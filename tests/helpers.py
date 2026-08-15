"""Fonctions au niveau module, utilisées par plusieurs fichiers de tests.

Un `ProcessPoolExecutor` exige des callables picklables donc importables
par leur chemin `module.qualname` — jamais une lambda, une closure, ou une
fonction imbriquée dans un test, qui échoueraient silencieusement à être
picklées (ou pire, pickleraient un objet différent de celui attendu).
"""

from __future__ import annotations

import os
import threading
import time

from django.contrib.auth.models import User

from django_goroutine import cpu, db, io


def square(n: int) -> int:
    return n * n


def boom(_: int) -> int:
    raise ValueError("boom")


def square_unless_two(n: int) -> int:
    if n == 2:
        raise ValueError("boom on 2")
    return n


@cpu
def current_process_id(_: int = 0) -> int:
    return os.getpid()


@db
def count_users() -> int:
    return User.objects.count()


@db
def get_user_by_username(username: str) -> int:
    return User.objects.get(username=username).pk


@db
def create_user_and_return_thread_name(username: str) -> str:
    User.objects.create(username=username)
    return threading.current_thread().name


@db
def read_and_return_thread_name() -> str:
    # sqlite ne supporte qu'un seul writer à la fois (verrou base entière) :
    # un test qui prouve la parallélisation du pool @db doit lire, pas
    # écrire, sous peine de "database is locked" — une limite du moteur
    # sqlite, pas du pool de threads lui-même (Postgres/MySQL encaissent
    # des écritures concurrentes sans ce verrou global).
    User.objects.count()
    return threading.current_thread().name


@db
def noop_db() -> int:
    return 1


@io
async def greet(name: str) -> str:
    return f"hello {name}"


@io
async def fail_io() -> None:
    raise ValueError("io boom")


@io
async def sleep_io(seconds: float, value: int) -> int:
    import asyncio

    await asyncio.sleep(seconds)
    return value


async def bare_coroutine(value: int) -> int:
    """Volontairement non décorée : `group().go()` doit la traiter comme `io`."""
    return value


@cpu
def sleep_cpu(seconds: float, value: int) -> int:
    time.sleep(seconds)
    return value


@cpu
def fail_cpu() -> None:
    raise ValueError("cpu boom")


def plain_sync(value: int) -> int:
    """Ni `@db`, ni `@cpu` : `group().go()` doit refuser de la dispatcher."""
    return value


@db
def sleep_db(seconds: float, value: int) -> int:
    time.sleep(seconds)
    return value


@db
def timestamped_sleep_db(seconds: float, value: int) -> tuple[float, float, int]:
    start = time.monotonic()
    time.sleep(seconds)
    end = time.monotonic()
    return (start, end, value)


@cpu
def crash_cpu_worker() -> None:
    """Tue durement son propre process — simule un worker qui crashe pour
    tester l'auto-récupération sur `BrokenProcessPool`."""
    os._exit(1)


@io
async def raise_timeout_io() -> None:
    """Lève un `TimeoutError` qui n'a rien à voir avec le mécanisme de
    timeout de django_goroutine (pas de `timeout=` fixé ici) — ne doit pas
    être confondu avec un dépassement de *notre* timeout."""
    raise TimeoutError("timeout métier, pas celui de django_goroutine")


@io(timeout=0.02)
async def slow_io_with_short_timeout() -> int:
    import asyncio

    await asyncio.sleep(0.3)
    return 1


@db(timeout=0.02)
def slow_db_with_short_timeout() -> int:
    time.sleep(0.3)
    return 1


@cpu(timeout=0.02)
def slow_cpu_with_short_timeout() -> int:
    time.sleep(0.3)
    return 1


def slow_square(n: int) -> int:
    time.sleep(0.3)
    return n * n


def crash_cpu_worker_item(_: int) -> None:
    """Équivalent de `crash_cpu_worker`, mais avec un paramètre : `cpu_map`
    appelle toujours `fn(item)`, jamais `fn()`."""
    os._exit(1)
