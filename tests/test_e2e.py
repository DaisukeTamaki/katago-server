from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from katago_server.config import Settings
from katago_server.engine import KataGoEngine
from katago_server.models import (
    AnalysisRequest,
    build_katago_query,
)

_settings = Settings()
_katago_available = (
    shutil.which(_settings.katago_binary) is not None
    and Path(_settings.model_path).exists()
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not _katago_available,
        reason=(
            f"KataGo binary '{_settings.katago_binary}' not on PATH "
            f"or model '{_settings.model_path}' not found"
        ),
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
            max_visits=5,
        )

        async def callback(response: dict) -> None:
            if not response.get("isDuringSearch", False):
                results.append(response)
                if len(results) >= 2:
                    done.set()

        await engine.submit_query(build_katago_query(request), callback)

        finished, _ = await asyncio.wait(
            [
                asyncio.create_task(done.wait()),
                asyncio.create_task(engine.crash_event.wait()),
            ],
            timeout=120,
            return_when=asyncio.FIRST_COMPLETED,
        )

        if engine.crash_event.is_set():
            pytest.fail(f"KataGo crashed: {engine.crash_reason}")
        if not finished:
            pytest.fail("Timed out waiting for KataGo response (120s)")

    assert len(results) == 2
    assert {r["turnNumber"] for r in results} == {0, 1}
