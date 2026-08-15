"""Pools persistants pour `@db` (threads) et `@cpu`/`cpu_map` (process).

Créés une seule fois et réutilisés entre les requêtes : c'est le
« réservoir de threads préconfiguré » qui manque à un `asyncio.gather` posé
à la main dans une vue Django, et ce qui évite de repayer le coût de spawn
d'un process (~50-100 ms) à chaque appel CPU-bound.
"""

from __future__ import annotations

import multiprocessing
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

import django

from django_goroutine.conf import app_settings

# "fork" (le défaut sur Linux) duplique le process tel quel, y compris ses
# threads en cours — ici le pool @db et la boucle asyncio. Si un de ces
# threads tenait un verrou interne (allocateur, logging...) au moment du
# fork, l'enfant en hérite déjà verrouillé pour toujours : blocage
# silencieux, jamais une erreur explicite. "spawn" démarre un interpréteur
# neuf à la place, plus lent au premier appel mais sans cet héritage.
_MP_CONTEXT = multiprocessing.get_context("spawn")


def _bootstrap_worker() -> None:  # pragma: no cover — tourne dans un process spawné
    """Initializer des process du pool @cpu.

    "spawn" démarre un interpréteur neuf qui réimporte à froid le module où
    vit la fonction @cpu picklée — sans avoir jamais appelé
    `django.setup()`. Si ce module importe, même indirectement, un modèle
    Django au niveau module, l'import casse avec `AppRegistryNotReady`
    avant même que la fonction @cpu ne s'exécute. `django.setup()` est
    idempotent (il vérifie en interne si les apps sont déjà prêtes), donc
    l'appeler ici systématiquement est sans risque — le même réflexe qu'un
    worker Celery. Hors de portée de coverage.py, qui ne suit pas
    l'exécution dans un process séparé.
    """
    django.setup()


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
        _cpu_executor = ProcessPoolExecutor(
            max_workers=app_settings.CPU_POOL_SIZE,
            mp_context=_MP_CONTEXT,
            initializer=_bootstrap_worker,
        )
    return _cpu_executor


def reset_executors() -> None:
    """Réservé aux tests et au rechargement de `GOROUTINE` : ferme les pools
    existants et force leur recréation au prochain accès.

    `wait=True` : attend l'arrêt effectif des threads/process avant de
    revenir. Pas un chemin chaud (test, rechargement de settings), et
    `wait=False` laissait les sémaphores du `ProcessPoolExecutor` fermés en
    différé — `multiprocessing.resource_tracker` finissait par les
    signaler comme fuités.
    """
    global _db_executor, _cpu_executor
    if _db_executor is not None:
        _db_executor.shutdown(wait=True)
        _db_executor = None
    if _cpu_executor is not None:
        _cpu_executor.shutdown(wait=True, cancel_futures=True)
        _cpu_executor = None
