"""Vues de démonstration — chacune illustre un seul aspect de
django-goroutine, voir examples/README.md pour la liste et le
raisonnement derrière chaque exemple."""

from __future__ import annotations

import time

from django.http import HttpRequest, HttpResponse, JsonResponse

from django_goroutine import cpu_map, group

from . import tasks

_LINKS = [
    ("/parallel/", "group() : @io + @db + @cpu en parallèle dans une seule vue"),
    ("/cpu-map/", "cpu_map() : un lot de calculs CPU-bound répartis sur les cœurs"),
    ("/timeout/", "Une tâche qui dépasse son timeout, sans planter la vue"),
    ("/errors/", "Une tâche qui échoue (Err), sans planter ses tâches sœurs"),
    (
        "/backpressure/",
        "Plus de tâches @db que DB_MAX_PENDING : elles attendent, ne s'empilent pas",
    ),
]


def index(request: HttpRequest) -> HttpResponse:
    items = "".join(
        f'<li><a href="{href}">{href}</a> — {desc}</li>' for href, desc in _LINKS
    )
    return HttpResponse(f"<h1>django-goroutine — playground</h1><ul>{items}</ul>")


async def parallel_view(request: HttpRequest) -> JsonResponse:
    start = time.monotonic()
    async with group() as g:
        price_task = g.go(tasks.fetch_remote_price, 1)
        count_task = g.go(tasks.count_articles)
        hash_task = g.go(tasks.compute_sha256, "django-goroutine")
    elapsed = time.monotonic() - start

    return JsonResponse(
        {
            "elapsed_seconds": round(elapsed, 3),
            "note": (
                "les trois tâches tournent en parallèle : elapsed_seconds "
                "≈ la plus lente des trois, pas leur somme"
            ),
            "remote_price": price_task.result().unwrap_or(None),
            "article_count": count_task.result().unwrap_or(None),
            "sha256": hash_task.result().unwrap_or(None),
        }
    )


async def cpu_map_view(request: HttpRequest) -> JsonResponse:
    payloads = [f"item-{i}" for i in range(8)]

    start = time.monotonic()
    results = await cpu_map(tasks.compute_sha256, payloads)
    elapsed = time.monotonic() - start

    return JsonResponse(
        {
            "elapsed_seconds": round(elapsed, 3),
            "items": len(payloads),
            "note": "réparti sur GOROUTINE['CPU_POOL_SIZE'] cœurs, pas un seul calcul",
            "results": [
                r.unwrap() if r.is_ok() else repr(r.unwrap_err()) for r in results
            ],
        }
    )


async def timeout_view(request: HttpRequest) -> JsonResponse:
    async with group() as g:
        handle = g.go(tasks.always_too_slow)
    result = handle.result()

    return JsonResponse(
        {
            "is_err": result.is_err(),
            "error": repr(result.unwrap_err()) if result.is_err() else None,
            "note": (
                "always_too_slow() dort 2s mais est décorée @io(timeout=0.05) : "
                "Err(TimeoutError) presque immédiatement, sans planter la vue"
            ),
        }
    )


async def errors_view(request: HttpRequest) -> JsonResponse:
    async with group() as g:
        ok_task = g.go(tasks.count_articles)
        fail_task = g.go(tasks.fetch_missing_article, 999_999)

    ok_result = ok_task.result()
    fail_result = fail_task.result()
    return JsonResponse(
        {
            "ok_task_succeeded": ok_result.is_ok(),
            "ok_task_value": ok_result.unwrap_or(None),
            "fail_task_failed": fail_result.is_err(),
            "fail_task_error": repr(fail_result.unwrap_err())
            if fail_result.is_err()
            else None,
            "note": "fail_task échoue (DoesNotExist) sans jamais affecter ok_task",
        }
    )


async def backpressure_view(request: HttpRequest) -> JsonResponse:
    start = time.monotonic()
    async with group() as g:
        handles = [g.go(tasks.slow_db_task, 0.2, i) for i in range(6)]
    elapsed = time.monotonic() - start

    return JsonResponse(
        {
            "elapsed_seconds": round(elapsed, 3),
            "tasks": len(handles),
            "note": (
                "GOROUTINE['DB_MAX_PENDING']=2 dans ce projet de démo : 6 tâches de "
                "0.2s ne tournent jamais plus de 2 à la fois, donc elapsed_seconds "
                "≈ 6/2 × 0.2s = 0.6s plutôt que 0.2s comme un groupe non bridé"
            ),
            "results": [h.result().unwrap() for h in handles],
        }
    )
