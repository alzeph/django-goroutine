from __future__ import annotations

import os
from concurrent.futures.process import BrokenProcessPool

from django_goroutine import cpu_map

from .helpers import (
    boom,
    crash_cpu_worker_item,
    current_process_id,
    slow_square,
    square,
    square_unless_two,
)


async def test_cpu_map_success():
    results = await cpu_map(square, [1, 2, 3])
    assert [r.unwrap() for r in results] == [1, 4, 9]


async def test_cpu_map_preserves_input_order():
    results = await cpu_map(square, range(10))
    assert [r.unwrap() for r in results] == [n * n for n in range(10)]


async def test_cpu_map_partial_failure_does_not_fail_the_batch():
    results = await cpu_map(square_unless_two, [1, 2, 3])
    assert results[0].unwrap() == 1
    assert results[1].is_err()
    assert isinstance(results[1].unwrap_err(), ValueError)
    assert results[2].unwrap() == 3


async def test_cpu_map_all_items_fail():
    results = await cpu_map(boom, [1, 2, 3])
    assert all(r.is_err() for r in results)


async def test_cpu_map_empty_iterable_returns_empty_list():
    assert await cpu_map(square, []) == []


async def test_cpu_map_runs_across_processes():
    results = await cpu_map(current_process_id, [1, 2])
    pids = {r.unwrap() for r in results}
    assert pids.isdisjoint({os.getpid()})


async def test_cpu_map_timeout_becomes_err():
    results = await cpu_map(slow_square, [1], timeout=0.02)
    assert results[0].is_err()
    assert isinstance(results[0].unwrap_err(), TimeoutError)


async def test_cpu_map_broken_process_pool_auto_recovers():
    results = await cpu_map(crash_cpu_worker_item, [1])
    assert results[0].is_err()
    assert isinstance(results[0].unwrap_err(), BrokenProcessPool)

    # Le pool a été réinitialisé automatiquement.
    recovered = await cpu_map(square, [5])
    assert recovered[0].unwrap() == 25
