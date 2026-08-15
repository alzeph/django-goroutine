from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

from django.apps import apps

from django_goroutine.executors import get_cpu_executor, get_db_executor


def test_ready_warms_both_pools():
    apps.get_app_config("django_goroutine").ready()

    assert isinstance(get_db_executor(), ThreadPoolExecutor)
    assert isinstance(get_cpu_executor(), ProcessPoolExecutor)
