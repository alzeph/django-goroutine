"""Décorateurs `io`/`db`/`cpu` : déclarent *comment* `group()` doit exécuter
une fonction, jamais *si* elle doit tourner en concurrence — cette décision
reste au point d'appel, via `Group.go()`, à la façon du mot-clé `go` en Go.

Chacun s'utilise nu (`@db`) ou paramétré (`@db(timeout=2.0)`) : un timeout
par défaut ne peut pas se poser sur `Group.go()` lui-même, puisque ses
`*args`/`**kwargs` sont déjà réservés au transfert vers la fonction décorée
— un appelant dont la fonction a elle-même un paramètre `timeout` s'en
trouverait sinon en collision.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Coroutine
from typing import Any, Literal, overload

GoroutineKind = Literal["io", "db", "cpu"]

_KIND_ATTR = "_goroutine_kind"
_TIMEOUT_ATTR = "_goroutine_timeout"

__all__ = ["GoroutineKind", "cpu", "db", "goroutine_kind", "goroutine_timeout", "io"]


@overload
def io[T, **P](
    fn: Callable[P, Coroutine[Any, Any, T]],
) -> Callable[P, Coroutine[Any, Any, T]]: ...


@overload
def io[T, **P](
    fn: None = None, *, timeout: float | None = None
) -> Callable[
    [Callable[P, Coroutine[Any, Any, T]]], Callable[P, Coroutine[Any, Any, T]]
]: ...


def io(fn: Callable[..., Any] | None = None, *, timeout: float | None = None) -> Any:
    """Marque une coroutine d'attente réseau/disque.

    `group().go()` l'exécute directement sur la boucle d'événements, sans
    thread ni process dédié — la tâche est suspendue pendant l'attente, pas
    bloquante. Une coroutine non décorée est de toute façon traitée comme
    `io` par défaut : ce marqueur sert surtout à documenter l'intention et,
    optionnellement, à fixer un `timeout` (secondes) au-delà duquel la
    tâche est abandonnée et son `TaskHandle.result()` devient
    `Err(TimeoutError(...))`.
    """

    def decorate(f: Callable[..., Any]) -> Callable[..., Any]:
        if not inspect.iscoroutinefunction(f):
            raise TypeError(f"@io ne peut décorer qu'une fonction async def, pas {f!r}")
        setattr(f, _KIND_ATTR, "io")
        setattr(f, _TIMEOUT_ATTR, timeout)
        return f

    return decorate(fn) if fn is not None else decorate


@overload
def db[T, **P](fn: Callable[P, T]) -> Callable[P, T]: ...


@overload
def db[T, **P](
    fn: None = None, *, timeout: float | None = None
) -> Callable[[Callable[P, T]], Callable[P, T]]: ...


def db(fn: Callable[..., Any] | None = None, *, timeout: float | None = None) -> Any:
    """Marque une fonction sync bloquante sur l'ORM.

    `group().go()` la dispatch sur le pool de threads dédié aux requêtes DB
    (`django_goroutine.executors.get_db_executor`), avec une connexion
    propre par thread et un nettoyage (`close_old_connections`) après
    chaque appel. Le nombre de tâches `@db` simultanément en file ou en
    cours est borné (`GOROUTINE["DB_MAX_PENDING"]`) : au-delà, un nouvel
    appel attend qu'une place se libère plutôt que de s'empiler sans
    limite. `timeout` (secondes) borne cette attente *et* l'exécution
    elle-même — au-delà, `TaskHandle.result()` devient
    `Err(TimeoutError(...))`. Un thread déjà en train d'exécuter la
    requête ORM au moment du timeout continue néanmoins jusqu'à sa fin en
    arrière-plan : Python ne peut pas interrompre de force un thread.
    """

    def decorate(f: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.iscoroutinefunction(f):
            raise TypeError(f"@db ne peut décorer qu'une fonction sync, pas {f!r}")
        setattr(f, _KIND_ATTR, "db")
        setattr(f, _TIMEOUT_ATTR, timeout)
        return f

    return decorate(fn) if fn is not None else decorate


@overload
def cpu[T, **P](fn: Callable[P, T]) -> Callable[P, T]: ...


@overload
def cpu[T, **P](
    fn: None = None, *, timeout: float | None = None
) -> Callable[[Callable[P, T]], Callable[P, T]]: ...


def cpu(fn: Callable[..., Any] | None = None, *, timeout: float | None = None) -> Any:
    """Marque une fonction sync CPU-bound.

    `group().go()` et `cpu_map()` la dispatchent sur le pool de process
    dédié (`django_goroutine.executors.get_cpu_executor`), hors du GIL. `fn`
    doit rester importable au niveau module et ses arguments/résultat
    picklables — contrainte de `ProcessPoolExecutor`, pas de ce décorateur.
    Comme pour `@db`, le nombre de tâches simultanément en file ou en cours
    est borné (`GOROUTINE["CPU_MAX_PENDING"]`), et `timeout` (secondes)
    borne l'attente et l'exécution — au-delà, `Err(TimeoutError(...))`. Un
    worker déjà lancé sur la tâche au moment du timeout continue en
    arrière-plan : un process séparé ne peut pas non plus être interrompu
    de force par ce mécanisme.
    """

    def decorate(f: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.iscoroutinefunction(f):
            raise TypeError(f"@cpu ne peut décorer qu'une fonction sync, pas {f!r}")
        setattr(f, _KIND_ATTR, "cpu")
        setattr(f, _TIMEOUT_ATTR, timeout)
        return f

    return decorate(fn) if fn is not None else decorate


def goroutine_kind(fn: Callable[..., Any]) -> GoroutineKind | None:
    """Lit le marqueur posé par `@io`/`@db`/`@cpu`.

    `None` si `fn` n'est pas décorée (cas normal pour une coroutine `io`
    implicite, ou une erreur d'appelant pour une fonction sync).
    """
    kind = getattr(fn, _KIND_ATTR, None)
    if kind in ("io", "db", "cpu"):
        return kind  # type: ignore[no-any-return]
    return None


def goroutine_timeout(fn: Callable[..., Any]) -> float | None:
    """Lit le `timeout` posé par `@io`/`@db`/`@cpu` appelé avec `timeout=...`.

    `None` si non décorée ou décorée sans `timeout` — `Group.go()` retombe
    alors sur `GOROUTINE["TASK_TIMEOUT"]` (le défaut global, lui-même
    `None` par défaut, donc pas de timeout du tout).
    """
    value = getattr(fn, _TIMEOUT_ATTR, None)
    return value if isinstance(value, int | float) else None
