from __future__ import annotations

import asyncio
import contextvars
import os
import threading
import time
from unittest import mock

import pytest
from django.contrib.auth.models import User
from pycatch import Ok

from django_goroutine import db, group, io
from django_goroutine.group import TaskHandle

from .helpers import (
    bare_coroutine,
    create_user_and_return_thread_name,
    current_process_id,
    fail_cpu,
    fail_io,
    get_user_by_username,
    greet,
    noop_db,
    plain_sync,
    read_and_return_thread_name,
    sleep_cpu,
    sleep_io,
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
