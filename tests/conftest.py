from __future__ import annotations

import pytest

from django_goroutine.conf import app_settings
from django_goroutine.executors import reset_executors


@pytest.fixture(autouse=True)
def _reset_goroutine_state():
    reset_executors()
    app_settings.reload()
    yield
    reset_executors()
    app_settings.reload()
