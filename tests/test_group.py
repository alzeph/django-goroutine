from __future__ import annotations

import asyncio
import contextvars
import os
import threading
import time
from concurrent.futures.process import BrokenProcessPool
from unittest import mock

import pytest
from django.contrib.auth.models import User
from pycatch import Ok

from django_goroutine import db, group, io
from django_goroutine.group import TaskHandle

from .helpers import (
    bare_coroutine,
    crash_cpu_worker,
    create_user_and_return_thread_name,
    current_process_id,
    fail_cpu,
    fail_io,
    get_user_by_username,
    greet,
    noop_db,
    plain_sync,
    raise_timeout_io,
    read_and_return_thread_name,
    sleep_cpu,
    sleep_io,
    slow_cpu_with_short_timeout,
    slow_db_with_short_timeout,
    slow_io_with_short_timeout,
    timestamped_sleep_db,
)

_ctx_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "_ctx_var", default="unset"
)


@io
async def _read_ctx_io() -> str:
    return _ctx_var.get()


@db
def _read_ctx_db() -> str:
    return _ctx_var.get()


# --- io -----------------------------------------------------------------


async def test_io_success():
    async with group() as g:
        handle = g.go(greet, "world")
    assert handle.result() == Ok("hello world")


async def test_io_failure_becomes_err():
    async with group() as g:
        handle = g.go(fail_io)
    result = handle.result()
    assert result.is_err()
    assert isinstance(result.unwrap_err(), ValueError)


async def test_bare_coroutine_is_treated_as_io():
    async with group() as g:
        handle = g.go(bare_coroutine, 42)
    assert handle.result() == Ok(42)


async def test_concurrent_io_tasks_run_in_parallel():
    start = time.monotonic()
    async with group() as g:
        handles = [g.go(sleep_io, 0.2, i) for i in range(3)]
    elapsed = time.monotonic() - start

    assert [h.result().unwrap() for h in handles] == [0, 1, 2]
    # Séquentiel aurait pris ~0.6s ; concurrent doit rester proche de 0.2s.
    assert elapsed < 0.45


# --- db -------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
async def test_db_success():
    async with group() as g:
        handle = g.go(noop_db)
    assert handle.result() == Ok(1)


@pytest.mark.django_db(transaction=True)
async def test_db_failure_becomes_err():
    async with group() as g:
        handle = g.go(get_user_by_username, "does-not-exist")
    result = handle.result()
    assert result.is_err()
    assert isinstance(result.unwrap_err(), User.DoesNotExist)


@pytest.mark.django_db(transaction=True)
async def test_db_task_runs_off_the_event_loop_thread():
    main_thread = threading.current_thread().name
    async with group() as g:
        handle = g.go(create_user_and_return_thread_name, "off-loop-user")
    assert handle.result().unwrap() != main_thread


@pytest.mark.django_db(transaction=True)
async def test_concurrent_db_tasks_use_distinct_threads():
    async with group() as g:
        handles = [g.go(read_and_return_thread_name) for _ in range(4)]
    thread_names = {h.result().unwrap() for h in handles}
    # thread_sensitive=False : les appels @db ne doivent pas être sérialisés
    # sur un seul thread, sinon le pool "réservoir" ne parallélise rien.
    assert len(thread_names) > 1


@pytest.mark.django_db(transaction=True)
async def test_db_task_closes_old_connections():
    with mock.patch("django_goroutine.group.close_old_connections") as spy:
        async with group() as g:
            g.go(noop_db)
    assert spy.called


async def test_io_task_inherits_contextvars():
    token = _ctx_var.set("io-value")
    try:
        async with group() as g:
            handle = g.go(_read_ctx_io)
        assert handle.result().unwrap() == "io-value"
    finally:
        _ctx_var.reset(token)


@pytest.mark.django_db(transaction=True)
async def test_db_task_inherits_contextvars():
    token = _ctx_var.set("db-value")
    try:
        async with group() as g:
            handle = g.go(_read_ctx_db)
        assert handle.result().unwrap() == "db-value"
    finally:
        _ctx_var.reset(token)


# --- cpu --------------------------------------------------------------------


async def test_cpu_success():
    async with group() as g:
        handle = g.go(sleep_cpu, 0.0, 21)
    assert handle.result() == Ok(21)


async def test_cpu_failure_becomes_err():
    async with group() as g:
        handle = g.go(fail_cpu)
    result = handle.result()
    assert result.is_err()
    assert isinstance(result.unwrap_err(), ValueError)


async def test_cpu_task_runs_in_a_separate_process():
    parent_pid = os.getpid()
    async with group() as g:
        handle = g.go(current_process_id)
    child_pid = handle.result().unwrap()
    assert child_pid != parent_pid


# --- dispatch errors et cycle de vie du handle ------------------------------


async def test_undecorated_sync_function_raises_type_error():
    async with group() as g:
        with pytest.raises(TypeError):
            g.go(plain_sync, 1)


def test_task_handle_result_before_group_exit_raises_runtime_error():
    async def _run() -> TaskHandle[int]:
        async with group() as g:
            handle = g.go(bare_coroutine, 1)
            with pytest.raises(RuntimeError):
                handle.result()
            return handle

    handle = asyncio.run(_run())
    assert handle.result() == Ok(1)


async def test_exception_in_host_code_cancels_siblings_and_raises_exception_group():
    with pytest.raises(ExceptionGroup):
        async with group() as g:
            g.go(sleep_io, 5, 0)
            raise ValueError("bug in the caller's own code, not in a dispatched task")


# --- timeout par tâche --------------------------------------------------


async def test_io_task_timeout_becomes_err():
    async with group() as g:
        handle = g.go(slow_io_with_short_timeout)
    result = handle.result()
    assert result.is_err()
    assert isinstance(result.unwrap_err(), TimeoutError)


@pytest.mark.django_db(transaction=True)
async def test_db_task_timeout_becomes_err():
    async with group() as g:
        handle = g.go(slow_db_with_short_timeout)
    result = handle.result()
    assert result.is_err()
    assert isinstance(result.unwrap_err(), TimeoutError)


async def test_cpu_task_timeout_becomes_err():
    async with group() as g:
        handle = g.go(slow_cpu_with_short_timeout)
    result = handle.result()
    assert result.is_err()
    assert isinstance(result.unwrap_err(), TimeoutError)


async def test_global_default_timeout_applies_without_explicit_decorator_timeout(
    settings,
):
    settings.GOROUTINE = {"TASK_TIMEOUT": 0.02}
    async with group() as g:
        handle = g.go(sleep_io, 0.3, 1)
    result = handle.result()
    assert result.is_err()
    assert isinstance(result.unwrap_err(), TimeoutError)


async def test_user_raised_timeout_error_is_not_confused_with_our_own():
    # Aucun timeout fixé (ni décorateur, ni GOROUTINE["TASK_TIMEOUT"]) :
    # le TimeoutError levé par la fonction elle-même doit remonter tel
    # quel, pas être réinterprété comme un dépassement de *notre* timeout.
    async with group() as g:
        handle = g.go(raise_timeout_io)
    result = handle.result()
    assert result.is_err()
    err = result.unwrap_err()
    assert isinstance(err, TimeoutError)
    assert str(err) == "timeout métier, pas celui de django_goroutine"


# --- backpressure ---------------------------------------------------------


@pytest.mark.django_db(transaction=True)
async def test_db_backpressure_serializes_beyond_max_pending(settings):
    settings.GOROUTINE = {"DB_MAX_PENDING": 1}
    async with group() as g:
        handles = [g.go(timestamped_sleep_db, 0.15, i) for i in range(2)]
    runs = sorted((h.result().unwrap() for h in handles), key=lambda r: r[0])
    (first_start, first_end, _), (second_start, _, _) = runs
    # DB_MAX_PENDING=1 : la deuxième tâche ne doit démarrer qu'une fois la
    # première terminée, même si DB_POOL_SIZE permettrait davantage de
    # threads simultanés — c'est le sémaphore de backpressure qui limite
    # ici, pas la taille du pool.
    assert second_start >= first_end - 0.02
    assert first_start < first_end


# --- auto-récupération sur pool @cpu cassé --------------------------------


async def test_cpu_broken_process_pool_auto_recovers():
    async with group() as g:
        handle = g.go(crash_cpu_worker)
    result = handle.result()
    assert result.is_err()
    assert isinstance(result.unwrap_err(), BrokenProcessPool)

    # Le pool a été réinitialisé automatiquement : un appel suivant doit
    # retrouver un pool sain plutôt que rester cassé indéfiniment.
    async with group() as g2:
        handle2 = g2.go(sleep_cpu, 0.0, 99)
    assert handle2.result() == Ok(99)
