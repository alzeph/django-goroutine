"""Pools persistants pour `@db` (threads) et `@cpu`/`cpu_map` (process).

Créés une seule fois et réutilisés entre les requêtes : c'est le
« réservoir de threads préconfiguré » qui manque à un `asyncio.gather` posé
à la main dans une vue Django, et ce qui évite de repayer le coût de spawn
d'un process (~50-100 ms) à chaque appel CPU-bound.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

from django_goroutine.conf import app_settings

__all__ = ["get_cpu_executor", "get_db_executor", "reset_executors"]

_db_executor: ThreadPoolExecutor | None = None
_cpu_executor: ProcessPoolExecutor | None = None


def get_db_executor() -> ThreadPoolExecutor:
    global _db_executor
    if _db_executor is None:
        _db_executor = ThreadPoolExecutor(
            max_workers=app_settings.DB_POOL_SIZE, thread_name_prefix="goroutine-db"
        )
    return _db_executor


def get_cpu_executor() -> ProcessPoolExecutor:
    global _cpu_executor
    if _cpu_executor is None:
        _cpu_executor = ProcessPoolExecutor(max_workers=app_settings.CPU_POOL_SIZE)
    return _cpu_executor


def reset_executors() -> None:
    """Réservé aux tests et au rechargement de `GOROUTINE` : ferme les pools
    existants et force leur recréation au prochain accès."""
    global _db_executor, _cpu_executor
    if _db_executor is not None:
        _db_executor.shutdown(wait=False)
        _db_executor = None
    if _cpu_executor is not None:
        _cpu_executor.shutdown(wait=False, cancel_futures=True)
        _cpu_executor = None
