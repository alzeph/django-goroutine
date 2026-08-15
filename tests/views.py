from __future__ import annotations

from django.http import JsonResponse

from django_goroutine import cpu_map, group

from .helpers import count_users, greet, square


async def profile_view(request):
    async with group() as g:
        count_task = g.go(count_users)
        greeting_task = g.go(greet, "world")

    squares = await cpu_map(square, [1, 2, 3])

    return JsonResponse(
        {
            "user_count": count_task.result().unwrap(),
            "greeting": greeting_task.result().unwrap(),
            "squares": [r.unwrap() for r in squares],
        }
    )
