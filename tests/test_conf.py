from __future__ import annotations

import os

import pytest

from django_goroutine.conf import app_settings


def test_default_values_from_test_settings():
    # tests/settings.py fixe explicitement GOROUTINE, donc on ne teste pas
    # ici les valeurs par défaut de conf.DEFAULTS mais bien la lecture du
    # réglage utilisateur.
    assert app_settings.DB_POOL_SIZE == 4
    assert app_settings.CPU_POOL_SIZE == 2


def test_falls_back_to_default_when_key_absent(settings):
    settings.GOROUTINE = {"DB_POOL_SIZE": 7}
    assert app_settings.DB_POOL_SIZE == 7
    assert app_settings.CPU_POOL_SIZE == os.cpu_count() or 1


def test_override_settings_reloads(settings):
    settings.GOROUTINE = {"DB_POOL_SIZE": 99, "CPU_POOL_SIZE": 3}
    assert app_settings.DB_POOL_SIZE == 99
    assert app_settings.CPU_POOL_SIZE == 3


def test_unknown_setting_raises():
    with pytest.raises(AttributeError):
        _ = app_settings.DOES_NOT_EXIST


def test_unrelated_setting_change_does_not_reload(settings):
    assert app_settings.DB_POOL_SIZE == 4
    settings.DEBUG = not settings.DEBUG
    assert app_settings.DB_POOL_SIZE == 4
