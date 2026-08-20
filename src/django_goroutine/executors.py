"""Pools persistants pour `@db` (threads) et `@cpu`/`cpu_map` (process),
et sémaphores de backpressure associés.

Les pools sont créés une seule fois et réutilisés entre les requêtes :
c'est le « réservoir de threads préconfiguré » qui manque à un
`asyncio.gather` posé à la main dans une vue Django, et ce qui évite de
repayer le coût de spawn d'un process (~50-100 ms) à chaque appel
CPU-bound. Les sémaphores bornent combien de tâches peuvent être en file
ou en cours d'exécution sur chaque pool à un instant donné : sans cette
borne, un pic de charge empile les tâches en attente indéfiniment dans la
file interne du pool (croissance mémoire, latence qui explose) plutôt que
de faire simplement attendre les nouveaux appels qu'une place se libère.
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

import django

from django_goroutine.conf import app_settings

logger = logging.getLogger("django_goroutine")

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


__all__ = [
    "get_cpu_executor",
    "get_cpu_semaphore",
    "get_db_executor",
    "get_db_semaphore",
    "reset_cpu_executor",
    "reset_db_executor",
    "reset_executors",
]

_db_executor: ThreadPoolExecutor | None = None
_cpu_executor: ProcessPoolExecutor | None = None
_db_semaphore: asyncio.Semaphore | None = None
_cpu_semaphore: asyncio.Semaphore | None = None


def get_db_executor() -> ThreadPoolExecutor:
    global _db_executor
    if _db_executor is None:
        size = app_settings.DB_POOL_SIZE
        logger.info("django_goroutine: démarrage du pool @db (%d threads)", size)
        _db_executor = ThreadPoolExecutor(
            max_workers=size, thread_name_prefix="goroutine-db"
        )
    return _db_executor


def get_cpu_executor() -> ProcessPoolExecutor:
    global _cpu_executor
    if _cpu_executor is None:
        size = app_settings.CPU_POOL_SIZE
        logger.info("django_goroutine: démarrage du pool @cpu (%d process)", size)
        _cpu_executor = ProcessPoolExecutor(
            max_workers=size,
            mp_context=_MP_CONTEXT,
            initializer=_bootstrap_worker,
        )
    return _cpu_executor


def get_db_semaphore() -> asyncio.Semaphore:
    global _db_semaphore
    if _db_semaphore is None:
        limit = app_settings.DB_MAX_PENDING
        if limit is None:
            limit = app_settings.DB_POOL_SIZE * 4
        _db_semaphore = asyncio.Semaphore(limit)
    return _db_semaphore


def get_cpu_semaphore() -> asyncio.Semaphore:
    global _cpu_semaphore
    if _cpu_semaphore is None:
        limit = app_settings.CPU_MAX_PENDING
        if limit is None:
            limit = app_settings.CPU_POOL_SIZE * 4
        _cpu_semaphore = asyncio.Semaphore(limit)
    return _cpu_semaphore


def reset_db_executor() -> None:
    """Ferme le pool @db existant et force sa recréation au prochain accès.

    `wait=True` : attend l'arrêt effectif des threads avant de revenir. Pas
    un chemin chaud (test, rechargement de settings, auto-récupération).
    """
    global _db_executor, _db_semaphore
    if _db_executor is not None:
        _db_executor.shutdown(wait=True)
        _db_executor = None
    _db_semaphore = None


def reset_cpu_executor() -> None:
    """Ferme le pool @cpu existant et force sa recréation au prochain accès.

    Séparé de `reset_db_executor` pour l'auto-récupération : un pool @cpu
    cassé (`BrokenProcessPool`, un worker qui a crashé) ne doit pas obliger
    à recréer aussi le pool @db, qui n'a rien à voir.
    """
    global _cpu_executor, _cpu_semaphore
    if _cpu_executor is not None:
        _cpu_executor.shutdown(wait=True, cancel_futures=True)
        _cpu_executor = None
    _cpu_semaphore = None


def reset_executors() -> None:
    """Réservé aux tests, au rechargement de `GOROUTINE`, et à l'arrêt de
    l'application : ferme les deux pools et force leur recréation au
    prochain accès."""
    reset_db_executor()
    reset_cpu_executor()
