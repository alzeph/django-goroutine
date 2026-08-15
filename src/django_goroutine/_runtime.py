"""Utilitaire interne partagé entre `group.py` et `cpu_map.py` — pas de
l'API publique du package."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger("django_goroutine")

__all__ = ["await_with_timeout"]


async def await_with_timeout[T](
    awaitable: Coroutine[Any, Any, T], timeout: float | None, fn: Callable[..., Any]
) -> T:
    """Applique `timeout` s'il est fixé, sinon attend normalement.

    Convertit un dépassement en `TimeoutError` explicite et le relève
    (plutôt que de le renvoyer) : les appelants le laissent remonter
    jusqu'à leur propre `except Exception`, qui le transforme en `Err`
    comme n'importe quelle autre erreur — un seul chemin de conversion, pas
    un par nature de tâche. Séparé du cas `timeout is None` pour ne jamais
    confondre un `TimeoutError` interne à `fn` (un client HTTP qui a son
    propre timeout, par exemple) avec un dépassement de *notre* timeout.
    """
    if timeout is None:
        return await awaitable
    try:
        return await asyncio.wait_for(awaitable, timeout)
    except TimeoutError as exc:
        logger.warning("django_goroutine: tâche %r expirée après %ss", fn, timeout)
        wrapped = TimeoutError(f"{fn!r} a dépassé le timeout de {timeout}s")
        wrapped.__cause__ = exc
        raise wrapped from exc
