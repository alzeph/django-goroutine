"""Réglages `GOROUTINE`, paresseux et invalidés par `override_settings`."""

from __future__ import annotations

import os
from typing import Any, cast

from django.conf import settings
from django.test.signals import setting_changed

SETTINGS_KEY = "GOROUTINE"

DEFAULTS: dict[str, Any] = {
    # Taille du pool de threads dédié aux fonctions @db (une connexion ORM
    # propre par thread, réutilisée entre requêtes).
    "DB_POOL_SIZE": 10,
    # Taille du pool de process dédié aux fonctions @cpu et à cpu_map().
    "CPU_POOL_SIZE": os.cpu_count() or 1,
}


class Settings:
    """Accès paresseux au dict GOROUTINE, invalidé par override_settings."""

    def __init__(self, defaults: dict[str, Any]) -> None:
        self.defaults = defaults
        self._cached_attrs: set[str] = set()

    @property
    def user_settings(self) -> dict[str, Any]:
        return cast(dict[str, Any], getattr(settings, SETTINGS_KEY, {}))

    def __getattr__(self, attr: str) -> Any:
        if attr not in self.defaults:
            raise AttributeError(f"Réglage {SETTINGS_KEY} invalide : {attr!r}")
        try:
            value = self.user_settings[attr]
        except KeyError:
            value = self.defaults[attr]
        self._cached_attrs.add(attr)
        setattr(self, attr, value)
        return value

    def reload(self) -> None:
        for attr in self._cached_attrs:
            delattr(self, attr)
        self._cached_attrs.clear()


app_settings = Settings(DEFAULTS)


def _reload_settings(*, setting: str, **kwargs: Any) -> None:
    if setting == SETTINGS_KEY:
        app_settings.reload()
        from django_goroutine.executors import reset_executors

        reset_executors()


setting_changed.connect(_reload_settings)
