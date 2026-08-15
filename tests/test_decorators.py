from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

import pytest

from django_goroutine.decorators import cpu, db, goroutine_kind, io


def _make_sync_function() -> Callable[[], int]:
    """Une fonction sync fraîche : `io`/`db`/`cpu` mutent l'objet décoré en
    place (pas de wrapper), donc chaque test qui décore doit partir d'un
    objet à lui, sous peine de pollution entre tests."""

    def fn() -> int:
        return 1

    return fn


def _make_coroutine_function() -> Callable[[], Coroutine[Any, Any, int]]:
    async def fn() -> int:
        return 1

    return fn


def test_io_tags_coroutine():
    tagged = io(_make_coroutine_function())
    assert goroutine_kind(tagged) == "io"


def test_io_rejects_sync_function():
    with pytest.raises(TypeError):
        io(_make_sync_function())  # type: ignore[arg-type]


def test_db_tags_sync_function():
    tagged = db(_make_sync_function())
    assert goroutine_kind(tagged) == "db"


def test_db_rejects_coroutine():
    with pytest.raises(TypeError):
        db(_make_coroutine_function())  # type: ignore[arg-type]


def test_cpu_tags_sync_function():
    tagged = cpu(_make_sync_function())
    assert goroutine_kind(tagged) == "cpu"


def test_cpu_rejects_coroutine():
    with pytest.raises(TypeError):
        cpu(_make_coroutine_function())  # type: ignore[arg-type]


def test_goroutine_kind_none_for_undecorated_function():
    assert goroutine_kind(_make_sync_function()) is None


def test_decorator_works_on_instance_method():
    class Service:
        @db
        def fetch(self) -> int:
            return 42

    assert goroutine_kind(Service().fetch) == "db"
