from __future__ import annotations

import asyncio
import os

import pytest

from katago_server.config import Settings
from katago_server.engine import KataGoEngine
from katago_server.models import (
    AnalysisRequest,
    build_katago_query,
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not os.getenv("KATAGO_KATAGO_BINARY") or not os.getenv("KATAGO_MODEL_PATH"),
        reason="requires KATAGO_KATAGO_BINARY and KATAGO_MODEL_PATH",
    ),
]


@pytest.mark.asyncio
async def test_real_katago_smoke_query() -> None:
    settings = Settings()
    results: list[dict] = []
    done = asyncio.Event()

    async with KataGoEngine(settings) as engine:
        request = AnalysisRequest(
            id="e2e-smoke",
            moves=[{"color": "b", "position": (3, 3)}],
            analyze_turns=[0, 1],
            max_visits=10,
        )

        async def callback(response: dict) -> None:
            if not response.get("isDuringSearch", False):
                results.append(response)
                if len(results) >= 2:
                    done.set()

        await engine.submit_query(build_katago_query(request), callback)
        await asyncio.wait_for(done.wait(), timeout=30)

    assert len(results) == 2
    assert {result["turnNumber"] for result in results} == {0, 1}
