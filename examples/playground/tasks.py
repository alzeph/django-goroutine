"""Fonctions `@io`/`@db`/`@cpu` utilisées par les vues de démonstration.

Toutes au niveau module, jamais imbriquées dans une vue : `@cpu` exige des
fonctions picklables (contrainte de `ProcessPoolExecutor`), ce qu'une
fonction imbriquée ou une closure ne sont jamais.
"""

from __future__ import annotations

import asyncio
import hashlib
import time

from django_goroutine import cpu, db, io

from .models import Article


@io
async def fetch_remote_price(product_id: int) -> float:
    """Simule un appel réseau (une API de prix externe) avec `asyncio.sleep`."""
    await asyncio.sleep(0.3)
    return 19.99 + product_id


@db
def count_articles() -> int:
    return Article.objects.count()


@db
def fetch_missing_article(pk: int) -> str:
    """Lève `Article.DoesNotExist` pour un pk qui n'existe pas — sert à
    démontrer qu'une tâche `@db` en échec ne fait pas planter ses sœurs."""
    return Article.objects.get(pk=pk).title


@db
def slow_db_task(seconds: float, value: int) -> int:
    time.sleep(seconds)
    return value


@cpu
def compute_sha256(payload: str) -> str:
    """Calcul CPU-bound réel (pas juste un `sleep`), pour un gain mesurable
    sur `/cpu-map/`. Fonctionne aussi bien dispatchée seule via `@cpu` que
    passée telle quelle à `cpu_map()`, qui ignore le marqueur `@cpu`."""
    digest = payload.encode()
    for _ in range(200_000):
        digest = hashlib.sha256(digest).digest()
    return digest.hex()


@io(timeout=0.05)
async def always_too_slow() -> None:
    """Dépasse volontairement son timeout — sert la démo `/timeout/`."""
    await asyncio.sleep(2)
