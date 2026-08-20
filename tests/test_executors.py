from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

from django_goroutine.executors import (
    get_cpu_executor,
    get_cpu_semaphore,
    get_db_executor,
    get_db_semaphore,
    reset_cpu_executor,
    reset_db_executor,
    reset_executors,
)


def test_get_db_executor_is_a_singleton():
    first = get_db_executor()
    second = get_db_executor()
    assert first is second
    assert isinstance(first, ThreadPoolExecutor)


def test_get_cpu_executor_is_a_singleton():
    first = get_cpu_executor()
    second = get_cpu_executor()
    assert first is second
    assert isinstance(first, ProcessPoolExecutor)


def test_db_executor_sized_from_settings():
    executor = get_db_executor()
    # GOROUTINE["DB_POOL_SIZE"] dans tests/settings.py
    assert executor._max_workers == 4


def test_reset_executors_forces_recreation():
    first = get_db_executor()
    reset_executors()
    second = get_db_executor()
    assert first is not second


def test_reset_executors_is_a_noop_when_nothing_was_created():
    reset_executors()
    reset_executors()  # ne doit pas lever sur un second appel à vide


def test_setting_changed_resets_executors_via_conf(settings):
    first = get_db_executor()
    settings.GOROUTINE = {"DB_POOL_SIZE": 1, "CPU_POOL_SIZE": 1}
    second = get_db_executor()
    assert first is not second
    assert second._max_workers == 1


def test_get_db_semaphore_is_a_singleton():
    first = get_db_semaphore()
    second = get_db_semaphore()
    assert first is second
    assert isinstance(first, asyncio.Semaphore)


def test_get_cpu_semaphore_is_a_singleton():
    first = get_cpu_semaphore()
    second = get_cpu_semaphore()
    assert first is second
    assert isinstance(first, asyncio.Semaphore)


def test_db_semaphore_defaults_to_four_times_pool_size():
    # GOROUTINE["DB_POOL_SIZE"] = 4 dans tests/settings.py, DB_MAX_PENDING
    # non fixé => 4 * 4.
    assert get_db_semaphore()._value == 16


def test_db_semaphore_respects_explicit_max_pending(settings):
    settings.GOROUTINE = {"DB_MAX_PENDING": 3}
    assert get_db_semaphore()._value == 3


def test_db_semaphore_respects_explicit_zero_max_pending(settings):
    # `0` est une valeur explicite valide (bloque tout appel @db tant que
    # rien ne relâche le sémaphore) : elle ne doit pas retomber sur le
    # défaut calculé (DB_POOL_SIZE * 4) comme le ferait un `0 or default`.
    settings.GOROUTINE = {"DB_MAX_PENDING": 0}
    assert get_db_semaphore()._value == 0


def test_cpu_semaphore_respects_explicit_zero_max_pending(settings):
    settings.GOROUTINE = {"CPU_MAX_PENDING": 0}
    assert get_cpu_semaphore()._value == 0


def test_reset_db_executor_does_not_touch_cpu_executor():
    get_db_executor()
    cpu_before = get_cpu_executor()
    reset_db_executor()
    assert get_cpu_executor() is cpu_before


def test_reset_cpu_executor_does_not_touch_db_executor():
    db_before = get_db_executor()
    get_cpu_executor()
    reset_cpu_executor()
    assert get_db_executor() is db_before


def test_reset_db_executor_also_resets_its_semaphore():
    first = get_db_semaphore()
    reset_db_executor()
    second = get_db_semaphore()
    assert first is not second


def test_reset_cpu_executor_also_resets_its_semaphore():
    first = get_cpu_semaphore()
    reset_cpu_executor()
    second = get_cpu_semaphore()
    assert first is not second
