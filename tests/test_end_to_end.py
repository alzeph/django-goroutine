from __future__ import annotations

import pytest
from django.test import AsyncClient


@pytest.mark.django_db(transaction=True)
async def test_profile_view_wires_group_and_cpu_map_together():
    client = AsyncClient()

    response = await client.get("/profile/")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "user_count": 0,
        "greeting": "hello world",
        "squares": [1, 4, 9],
    }
