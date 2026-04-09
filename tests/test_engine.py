from __future__ import annotations

import pytest

from katago_server.config import Settings
from katago_server.engine import KataGoEngine, _QueryTracker


@pytest.mark.asyncio
async def test_submit_query_tracks_pending_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = KataGoEngine(Settings())
    written: list[dict] = []

    monkeypatch.setattr(engine, "_assert_running", lambda: None)
    monkeypatch.setattr(engine, "_write", lambda payload: written.append(payload))

    async def callback(_: dict) -> None:
        return None

    query = {"id": "query-1", "analyzeTurns": [0, 1]}
    await engine.submit_query(query, callback)

    assert written == [query]
    assert engine._queries["query-1"].pending_turns == {0, 1}


@pytest.mark.asyncio
async def test_dispatch_response_keeps_partial_results_and_cleans_final() -> None:
    engine = KataGoEngine(Settings())
    seen: list[dict] = []

    async def callback(response: dict) -> None:
        seen.append(response)

    engine._queries["query-1"] = _QueryTracker(callback=callback, pending_turns={0})

    await engine._dispatch_response(
        {"id": "query-1", "turnNumber": 0, "isDuringSearch": True}
    )
    assert len(seen) == 1
    assert "query-1" in engine._queries

    await engine._dispatch_response(
        {"id": "query-1", "turnNumber": 0, "isDuringSearch": False}
    )
    assert len(seen) == 2
    assert "query-1" not in engine._queries


@pytest.mark.asyncio
async def test_remove_queries_for_callback() -> None:
    engine = KataGoEngine(Settings())

    async def callback_a(_: dict) -> None:
        return None

    async def callback_b(_: dict) -> None:
        return None

    engine._queries = {
        "query-a": _QueryTracker(callback=callback_a, pending_turns={0}),
        "query-b": _QueryTracker(callback=callback_b, pending_turns={0}),
    }

    engine.remove_queries_for_callback(callback_a)

    assert set(engine._queries) == {"query-b"}
