"""`group()` : orchestrateur structuré au-dessus d'`asyncio.TaskGroup`.

L'équivalent, côté Django, du couple `go`/`sync.WaitGroup` de Go : le point
d'appel décide quoi lancer en concurrence (`Group.go()`), pas la fonction
elle-même — les décorateurs `io`/`db`/`cpu` ne font que déclarer *comment*
l'exécuter. Chaque tâche renvoie un `pycatch.Result` plutôt que de lever :
un échec business sur une tâche ne fait jamais planter ses sœurs.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
from collections.abc import Callable, Coroutine
from types import TracebackType
from typing import Any, overload

from asgiref.sync import sync_to_async
from django.db import close_old_connections
from pycatch import Err, Ok, Result

from django_goroutine.decorators import GoroutineKind, goroutine_kind
from django_goroutine.executors import get_cpu_executor, get_db_executor

__all__ = ["Group", "TaskHandle", "group"]


async def _run_io[T](
    fn: Callable[..., Coroutine[Any, Any, T]],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Result[T, Exception]:
    try:
        return Ok(await fn(*args, **kwargs))
    except Exception as exc:  # noqa: BLE001 - toute exception business devient un Err
        return Err(exc)


async def _run_db[T](
    fn: Callable[..., T], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> Result[T, Exception]:
    executor = get_db_executor()
    bound = sync_to_async(fn, thread_sensitive=False, executor=executor)
    try:
        return Ok(await bound(*args, **kwargs))
    except Exception as exc:  # noqa: BLE001
        return Err(exc)
    finally:
        # Rend la connexion du thread réutilisable pour le prochain appel
        # sans la garder indéfiniment si elle a expiré (CONN_MAX_AGE) ou
        # est devenue inutilisable — jamais un close_all() inconditionnel,
        # qui casserait l'intérêt même d'un pool de threads persistant.
        cleanup = sync_to_async(
            close_old_connections, thread_sensitive=False, executor=executor
        )
        await cleanup()


async def _run_cpu[T](
    fn: Callable[..., T], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> Result[T, Exception]:
    loop = asyncio.get_running_loop()
    try:
        value = await loop.run_in_executor(
            get_cpu_executor(), functools.partial(fn, *args, **kwargs)
        )
        return Ok(value)
    except Exception as exc:  # noqa: BLE001
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
