"""Décorateurs `io`/`db`/`cpu` : déclarent *comment* `group()` doit exécuter
une fonction, jamais *si* elle doit tourner en concurrence — cette décision
reste au point d'appel, via `Group.go()`, à la façon du mot-clé `go` en Go.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Coroutine
from typing import Any, Literal

GoroutineKind = Literal["io", "db", "cpu"]

_KIND_ATTR = "_goroutine_kind"

__all__ = ["GoroutineKind", "cpu", "db", "goroutine_kind", "io"]


def io[T, **P](
    fn: Callable[P, Coroutine[Any, Any, T]],
) -> Callable[P, Coroutine[Any, Any, T]]:
    """Marque une coroutine d'attente réseau/disque.

    `group().go()` l'exécute directement sur la boucle d'événements, sans
    thread ni process dédié — la tâche est suspendue pendant l'attente, pas
    bloquante. Une coroutine non décorée est de toute façon traitée comme
    `io` par défaut : ce marqueur documente l'intention plus qu'il ne change
    le comportement.
    """
    if not inspect.iscoroutinefunction(fn):
        raise TypeError(f"@io ne peut décorer qu'une fonction async def, pas {fn!r}")
    setattr(fn, _KIND_ATTR, "io")
    return fn


def db[T, **P](fn: Callable[P, T]) -> Callable[P, T]:
    """Marque une fonction sync bloquante sur l'ORM.

    `group().go()` la dispatch sur le pool de threads dédié aux requêtes DB
    (`django_goroutine.executors.get_db_executor`), avec une connexion
    propre par thread et un nettoyage (`close_old_connections`) après
    chaque appel.
    """
    if inspect.iscoroutinefunction(fn):
        raise TypeError(f"@db ne peut décorer qu'une fonction sync, pas {fn!r}")
    setattr(fn, _KIND_ATTR, "db")
    return fn


def cpu[T, **P](fn: Callable[P, T]) -> Callable[P, T]:
    """Marque une fonction sync CPU-bound.

    `group().go()` et `cpu_map()` la dispatchent sur le pool de process
    dédié (`django_goroutine.executors.get_cpu_executor`), hors du GIL. `fn`
    doit rester importable au niveau module et ses arguments/résultat
    picklables — contrainte de `ProcessPoolExecutor`, pas de ce décorateur.
    """
    if inspect.iscoroutinefunction(fn):
        raise TypeError(f"@cpu ne peut décorer qu'une fonction sync, pas {fn!r}")
    setattr(fn, _KIND_ATTR, "cpu")
    return fn


def goroutine_kind(fn: Callable[..., Any]) -> GoroutineKind | None:
    """Lit le marqueur posé par `@io`/`@db`/`@cpu`.

    `None` si `fn` n'est pas décorée (cas normal pour une coroutine `io`
    implicite, ou une erreur d'appelant pour une fonction sync).
    """
    kind = getattr(fn, _KIND_ATTR, None)
    if kind in ("io", "db", "cpu"):
        return kind  # type: ignore[no-any-return]
    return None
