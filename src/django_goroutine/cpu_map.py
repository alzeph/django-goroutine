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
from collections.abc import Callable, Iterable
from typing import Any

from pycatch import Err, Ok, Result

from django_goroutine.executors import get_cpu_executor

__all__ = ["cpu_map"]


async def cpu_map[T, R](
    fn: Callable[[T], R], items: Iterable[T]
) -> list[Result[R, Exception]]:
    """Applique `fn` à chaque élément de `items` en parallèle sur le pool de process.

    `fn` doit être une fonction sync CPU-bound, importable au niveau module
    (contrainte de `pickle` du `ProcessPoolExecutor` sous-jacent) — ni une
    lambda, ni une closure, ni une méthode d'instance liée. Un échec sur un
    élément ne fait pas échouer les autres : chaque résultat est un
    `Result` indépendant, dans l'ordre de `items`.
    """
    loop = asyncio.get_running_loop()
    executor = get_cpu_executor()
    futures = [loop.run_in_executor(executor, fn, item) for item in items]
    if not futures:
        return []
    settled: list[Any] = await asyncio.gather(*futures, return_exceptions=True)
    return [Err(r) if isinstance(r, Exception) else Ok(r) for r in settled]
