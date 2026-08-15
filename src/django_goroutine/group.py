"""`group()` : orchestrateur structuré au-dessus d'`asyncio.TaskGroup`.

L'équivalent, côté Django, du couple `go`/`sync.WaitGroup` de Go : le point
d'appel décide quoi lancer en concurrence (`Group.go()`), pas la fonction
elle-même — les décorateurs `io`/`db`/`cpu` ne font que déclarer *comment*
l'exécuter. Chaque tâche renvoie un `pycatch.Result` plutôt que de lever :
un échec business, un timeout ou un pool `@cpu` cassé sur une tâche ne
font jamais planter ses sœurs.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
from collections.abc import Callable, Coroutine
from concurrent.futures.process import BrokenProcessPool
from types import TracebackType
from typing import Any, overload

from asgiref.sync import sync_to_async
from django.db import close_old_connections
from pycatch import Err, Ok, Result

from django_goroutine._runtime import await_with_timeout
from django_goroutine.conf import app_settings
from django_goroutine.decorators import GoroutineKind, goroutine_kind, goroutine_timeout
from django_goroutine.executors import (
    get_cpu_executor,
    get_cpu_semaphore,
    get_db_executor,
    get_db_semaphore,
    reset_cpu_executor,
)

__all__ = ["Group", "TaskHandle", "group"]

logger = logging.getLogger("django_goroutine")


def _resolve_timeout(fn: Callable[..., Any]) -> float | None:
    explicit = goroutine_timeout(fn)
    return explicit if explicit is not None else app_settings.TASK_TIMEOUT


async def _run_io[T](
    fn: Callable[..., Coroutine[Any, Any, T]],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Result[T, Exception]:
    timeout = _resolve_timeout(fn)
    try:
        value = await await_with_timeout(fn(*args, **kwargs), timeout, fn)
        return Ok(value)
    except Exception as exc:  # noqa: BLE001 - toute exception business devient un Err
        logger.debug("django_goroutine: tâche @io %r échouée: %r", fn, exc)
        return Err(exc)


async def _run_db[T](
    fn: Callable[..., T], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> Result[T, Exception]:
    timeout = _resolve_timeout(fn)

    async def call() -> T:
        # Le sémaphore borne combien d'appels @db sont en file ou en cours
        # à la fois (backpressure) : au-delà, ce `async with` fait
        # attendre l'appelant plutôt que d'empiler sans limite dans la
        # file interne du ThreadPoolExecutor. En cas de timeout, il est
        # déjà libéré (l'annulation traverse le `async with`) — mais si
        # l'appel avait déjà atteint le thread, celui-ci continue
        # d'exécuter la requête ORM en arrière-plan jusqu'à sa fin :
        # Python ne peut pas interrompre de force un thread.
        async with get_db_semaphore():

            def call_and_close_stale_connection() -> T:
                try:
                    return fn(*args, **kwargs)
                finally:
                    # `django.db.connections` est thread-local : ce
                    # nettoyage doit tourner sur le *même* thread que
                    # l'appel ci-dessus, sinon il ne voit pas la connexion
                    # qu'il est censé fermer. D'où un seul sync_to_async
                    # englobant les deux, plutôt que deux dispatches
                    # séparés vers un pool où rien ne garantit le même
                    # thread. Jamais un close_all() inconditionnel non
                    # plus, qui casserait l'intérêt même d'un pool de
                    # threads/connexions persistant.
                    close_old_connections()

            bound = sync_to_async(
                call_and_close_stale_connection,
                thread_sensitive=False,
                executor=get_db_executor(),
            )
            return await bound()

    try:
        value = await await_with_timeout(call(), timeout, fn)
        return Ok(value)
    except Exception as exc:  # noqa: BLE001
        logger.debug("django_goroutine: tâche @db %r échouée: %r", fn, exc)
        return Err(exc)


async def _run_cpu[T](
    fn: Callable[..., T], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> Result[T, Exception]:
    timeout = _resolve_timeout(fn)

    async def call() -> T:
        # Même logique de backpressure que @db, sur le pool de process.
        # Même réserve sur le timeout : un worker déjà lancé sur la tâche
        # continue en arrière-plan dans son process, un `Future` annulé
        # après coup ne l'interrompt pas de force.
        async with get_cpu_semaphore():
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                get_cpu_executor(), functools.partial(fn, *args, **kwargs)
            )

    try:
        value = await await_with_timeout(call(), timeout, fn)
        return Ok(value)
    except BrokenProcessPool as exc:
        # Un worker a crashé durement (segfault, os._exit...) : le pool
        # entier est inutilisable tant qu'il n'est pas recréé. Pas de
        # retry automatique de cet appel (rejouer une fonction qui a peut-
        # être déjà eu des effets de bord serait pire), mais le prochain
        # appel récupère un pool sain plutôt que de rester cassé pour de
        # bon.
        logger.error("django_goroutine: pool @cpu cassé (%r), réinitialisation", exc)
        reset_cpu_executor()
        return Err(exc)
    except Exception as exc:  # noqa: BLE001
        logger.debug("django_goroutine: tâche @cpu %r échouée: %r", fn, exc)
        return Err(exc)


_Runner = Callable[..., Coroutine[Any, Any, Result[Any, Exception]]]
_RUNNERS: dict[GoroutineKind, _Runner] = {
    "io": _run_io,
    "db": _run_db,
    "cpu": _run_cpu,
}


class TaskHandle[T]:
    """Poignée renvoyée par `Group.go()`.

    Le `Result` n'est lisible qu'une fois le bloc `async with group()`
    refermé (`asyncio.TaskGroup` attend la fin de toutes les tâches à la
    sortie du bloc) — appeler `result()` avant lève `RuntimeError`.
    """

    __slots__ = ("_task",)

    def __init__(self, task: asyncio.Task[Result[T, Exception]]) -> None:
        self._task = task

    def result(self) -> Result[T, Exception]:
        if not self._task.done():
            raise RuntimeError(
                "TaskHandle.result() appelé avant la sortie du bloc "
                "`async with group()` — le résultat n'existe pas encore."
            )
        return self._task.result()


class Group:
    """Un groupe de tâches concurrentes, à utiliser via `async with group() as g:`.

    N'importe quelle exception levée par une tâche dispatchée devient un
    `Err` porté par son `TaskHandle` : elle ne fait jamais planter les
    tâches sœurs ni le bloc englobant — c'est un `sync.WaitGroup`, pas un
    `errgroup` à annulation automatique sur erreur métier. L'annulation
    reste possible, mais seulement de façon structurelle : si le bloc
    `async with group()` lui-même est annulé de l'extérieur (timeout du
    serveur ASGI, déconnexion client), les tâches encore en cours sont
    annulées par `asyncio.TaskGroup`, comme n'importe quel autre `await`.

    Un timeout individuel par tâche (`@db(timeout=2.0)`, ou
    `GOROUTINE["TASK_TIMEOUT"]` par défaut) et une borne sur le nombre de
    tâches `@db`/`@cpu` simultanément en file ou en cours
    (`GOROUTINE["DB_MAX_PENDING"]`/`CPU_MAX_PENDING`) s'ajoutent à ce
    mécanisme sans le remplacer.
    """

    __slots__ = ("_task_group",)

    def __init__(self) -> None:
        self._task_group = asyncio.TaskGroup()

    async def __aenter__(self) -> Group:
        await self._task_group.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        # TaskGroup.__aexit__ ne supprime jamais une exception (elle
        # continue toujours de se propager si elle en contenait une) : pas
        # de valeur de retour à relayer ici.
        await self._task_group.__aexit__(exc_type, exc, tb)

    @overload
    def go[T, **P](
        self,
        fn: Callable[P, Coroutine[Any, Any, T]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> TaskHandle[T]: ...

    @overload
    def go[T, **P](
        self, fn: Callable[P, T], *args: P.args, **kwargs: P.kwargs
    ) -> TaskHandle[T]: ...

    def go(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> TaskHandle[Any]:
        kind = goroutine_kind(fn)
        if kind is None:
            if not inspect.iscoroutinefunction(fn):
                raise TypeError(
                    f"{fn!r} n'est ni une coroutine ni décorée avec @db ou @cpu : "
                    "impossible de savoir sur quel pool l'exécuter."
                )
            kind = "io"
        runner = _RUNNERS[kind]
        task = self._task_group.create_task(runner(fn, args, kwargs))
        return TaskHandle(task)


def group() -> Group:
    """Ouvre un groupe de tâches concurrentes, borné par un `async with`.

    Exemple :
        async with group() as g:
            user_task = g.go(fetch_user, user_id)
            avatar_task = g.go(fetch_avatar, avatar_url)

        match user_task.result():
            case Ok(user): ...
            case Err(err): ...
    """
    return Group()
