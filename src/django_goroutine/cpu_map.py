"""`cpu_map()` : parallélise un calcul CPU-bound décomposable.

`group().go()` avec `@cpu` ne fait gagner du temps que sur du travail déjà
découpé en unités indépendantes — une seule fonction CPU-bound n'accélère
pas en la dispatchant seule, exactement comme une goroutine Go seule
n'accélère pas un calcul monolithique. `cpu_map()` couvre le cas où ce
découpage existe déjà : un lot d'entrées indépendantes (N images, N
documents...) à traiter en parallèle sur les cœurs disponibles.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine, Iterable
from concurrent.futures.process import BrokenProcessPool
from typing import Any

from pycatch import Err, Ok, Result

from django_goroutine._runtime import await_with_timeout
from django_goroutine.executors import (
    get_cpu_executor,
    get_cpu_semaphore,
    reset_cpu_executor,
)

__all__ = ["cpu_map"]

logger = logging.getLogger("django_goroutine")


async def _map_one[T, R](
    fn: Callable[[T], R], item: T, timeout: float | None
) -> Result[R, Exception]:
    async def call() -> R:
        # Même sémaphore que les tâches @cpu de group() : cpu_map() et
        # @cpu se partagent la même borne de backpressure sur le pool de
        # process, ils se disputent la même ressource.
        async with get_cpu_semaphore():
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(get_cpu_executor(), fn, item)

    try:
        value = await await_with_timeout(call(), timeout, fn)
        return Ok(value)
    except BrokenProcessPool as exc:
        logger.error("django_goroutine: pool @cpu cassé (%r), réinitialisation", exc)
        reset_cpu_executor()
        return Err(exc)
    except Exception as exc:  # noqa: BLE001
        logger.debug("django_goroutine: cpu_map(%r) échoué sur un élément: %r", fn, exc)
        return Err(exc)


async def cpu_map[T, R](
    fn: Callable[[T], R], items: Iterable[T], *, timeout: float | None = None
) -> list[Result[R, Exception]]:
    """Applique `fn` à chaque élément de `items` en parallèle sur le pool de process.

    `fn` doit être une fonction sync CPU-bound, importable au niveau module
    (contrainte de `pickle` du `ProcessPoolExecutor` sous-jacent) — ni une
    lambda, ni une closure, ni une méthode d'instance liée. Un échec sur un
    élément, y compris un dépassement de `timeout` (secondes, appliqué
    individuellement à chaque élément) ou un pool cassé
    (`BrokenProcessPool`, auto-réinitialisé pour les appels suivants), ne
    fait pas échouer les autres : chaque résultat est un `Result`
    indépendant, dans l'ordre de `items`.
    """
    coros: list[Coroutine[Any, Any, Result[R, Exception]]] = [
        _map_one(fn, item, timeout) for item in items
    ]
    if not coros:
        return []
    return await asyncio.gather(*coros)
