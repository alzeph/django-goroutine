from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

from django_goroutine.executors import (
    get_cpu_executor,
    get_db_executor,
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
