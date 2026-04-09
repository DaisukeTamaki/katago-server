"""MCP server exposing KataGo analysis as LLM tools."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

from katago_server.config import settings
from katago_server.engine import KataGoEngine
from katago_server.models import (
    AnalysisRequest,
    StonePosition,
    build_katago_query,
)


@dataclass
class AppContext:
    engine: KataGoEngine


@asynccontextmanager
async def _lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    engine = KataGoEngine(settings)
    await engine.start()
    try:
        yield AppContext(engine=engine)
    finally:
        await engine.stop()


mcp = FastMCP(
    "katago-server",
    instructions=(
        "Go (Baduk/Weiqi) game analysis powered by KataGo. "
        "Positions use (row, col) coordinates, 0-indexed from the bottom-left. "
        "Colors are 'b' for black, 'w' for white."
    ),
    lifespan=_lifespan,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_stones(raw: list[dict[str, Any]]) -> list[StonePosition]:
    return [StonePosition(color=s["color"], position=tuple(s["position"])) for s in raw]


@dataclass
class _ResultCollector:
    """Collects KataGo responses for a query until all turns are done."""

    results: list[dict] = field(default_factory=list)
    done: asyncio.Event = field(default_factory=asyncio.Event)

    async def callback(self, response: dict) -> None:
        is_during_search = response.get("isDuringSearch", False)
        if not is_during_search:
            self.results.append(response)


async def _run_query(
    engine: KataGoEngine,
    request: AnalysisRequest,
) -> list[dict]:
    """Submit a query to KataGo and wait for all final results."""
    collector = _ResultCollector()
    expected = len(request.analyze_turns) if request.analyze_turns else 1

    query = build_katago_query(request)
    await engine.submit_query(query, collector.callback)

    for _ in range(300):
        if len(collector.results) >= expected:
            break
        await asyncio.sleep(0.1)

    return sorted(collector.results, key=lambda r: r.get("turnNumber", 0))


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def analyze_position(
    ctx: Context[ServerSession, AppContext],
    moves: list[dict[str, Any]] | None = None,
    initial_stones: list[dict[str, Any]] | None = None,
    initial_player: str | None = None,
    komi: float = 6.5,
    board_size: int = 19,
    rules: str = "tromp-taylor",
    max_visits: int | None = None,
    include_ownership: bool = False,
    include_policy: bool = False,
) -> str:
    """Analyze a Go board position.

    Returns best moves with win rates, scores, and principal variations.

    Args:
        moves: Game move sequence. Each dict has "color" ('b'/'w') and "position" [row, col].
        initial_stones: Stones on the board without move history (e.g., from a board photo).
        initial_player: Who plays next ('b' or 'w'). Needed when moves is empty.
        komi: Komi value (default 6.5).
        board_size: Board size (9, 13, or 19).
        rules: Ruleset (e.g., 'tromp-taylor', 'chinese', 'japanese').
        max_visits: Max search visits. Higher = stronger but slower.
        include_ownership: Include per-point territory ownership predictions.
        include_policy: Include raw neural network policy.
    """
    engine = ctx.request_context.lifespan_context.engine

    request = AnalysisRequest(
        id=str(uuid.uuid4()),
        moves=_parse_stones(moves or []),
        initial_stones=_parse_stones(initial_stones or []),
        initial_player=initial_player,
        komi=komi,
        board_size_x=board_size,
        board_size_y=board_size,
        rules=rules,
        max_visits=max_visits,
        include_ownership=include_ownership,
        include_policy=include_policy,
    )

    results = await _run_query(engine, request)
    return json.dumps(results, indent=2)


@mcp.tool()
async def analyze_human_move(
    ctx: Context[ServerSession, AppContext],
    moves: list[dict[str, Any]] | None = None,
    initial_stones: list[dict[str, Any]] | None = None,
    initial_player: str | None = None,
    human_rank: str = "rank_5k",
    komi: float = 6.5,
    board_size: int = 19,
    max_visits: int | None = None,
) -> str:
    """Predict what a human at a given rank would play, and compare with the optimal move.

    Uses KataGo's human SL model to predict moves at the configured strength.
    The response includes both the engine's best moves and the human policy
    (humanPrior) for each move, showing what a player of the given rank would likely play.

    Args:
        moves: Game move sequence. Each dict has "color" ('b'/'w') and "position" [row, col].
        initial_stones: Stones on the board without move history.
        initial_player: Who plays next ('b' or 'w').
        human_rank: KataGo human SL profile. Examples: 'rank_20k' through 'rank_9d',
                    'preaz_20k' through 'preaz_9d', 'proyear_1800' through 'proyear_2023'.
        komi: Komi value.
        board_size: Board size.
        max_visits: Max search visits.
    """
    engine = ctx.request_context.lifespan_context.engine

    request = AnalysisRequest(
        id=str(uuid.uuid4()),
        moves=_parse_stones(moves or []),
        initial_stones=_parse_stones(initial_stones or []),
        initial_player=initial_player,
        komi=komi,
        board_size_x=board_size,
        board_size_y=board_size,
        max_visits=max_visits,
        include_policy=True,
        override_settings={
            "humanSLProfile": human_rank,
            "ignorePreRootHistory": False,
            "humanSLRootExploreProbWeightless": 0.5,
            "humanSLCpuctPermanent": 2.0,
        },
    )

    results = await _run_query(engine, request)
    return json.dumps(results, indent=2)


@mcp.tool()
async def compare_moves(
    ctx: Context[ServerSession, AppContext],
    moves: list[dict[str, Any]],
    move_a: dict[str, Any],
    move_b: dict[str, Any],
    komi: float = 6.5,
    board_size: int = 19,
    max_visits: int | None = None,
) -> str:
    """Compare two candidate moves by analyzing the position after each one.

    Useful for "what if" analysis: compare the best move vs the move actually played,
    or compare two candidate moves to see how they differ.

    Args:
        moves: Game move sequence up to the point of comparison.
        move_a: First move to compare. Dict with "color" ('b'/'w') and "position" [row, col].
        move_b: Second move to compare. Same format.
        komi: Komi value.
        board_size: Board size.
        max_visits: Max search visits per position.
    """
    engine = ctx.request_context.lifespan_context.engine

    stones_base = _parse_stones(moves)
    stone_a = StonePosition(color=move_a["color"], position=tuple(move_a["position"]))
    stone_b = StonePosition(color=move_b["color"], position=tuple(move_b["position"]))

    async def analyze_branch(extra_move: StonePosition, label: str) -> dict:
        request = AnalysisRequest(
            id=str(uuid.uuid4()),
            moves=stones_base + [extra_move],
            komi=komi,
            board_size_x=board_size,
            board_size_y=board_size,
            max_visits=max_visits,
        )
        results = await _run_query(engine, request)
        return {"label": label, "move": extra_move.model_dump(), "analysis": results}

    branch_a, branch_b = await asyncio.gather(
        analyze_branch(stone_a, "move_a"),
        analyze_branch(stone_b, "move_b"),
    )

    return json.dumps({"comparison": [branch_a, branch_b]}, indent=2)


@mcp.tool()
async def evaluate_variation(
    ctx: Context[ServerSession, AppContext],
    moves: list[dict[str, Any]],
    komi: float = 6.5,
    board_size: int = 19,
    max_visits: int | None = None,
) -> str:
    """Evaluate a sequence of moves, returning analysis at each step.

    Analyzes every turn in the move sequence so you can see how the evaluation
    (win rate, score) changes move by move.

    Args:
        moves: Full move sequence to evaluate. Each dict has "color" and "position".
        komi: Komi value.
        board_size: Board size.
        max_visits: Max search visits per position.
    """
    engine = ctx.request_context.lifespan_context.engine

    request = AnalysisRequest(
        id=str(uuid.uuid4()),
        moves=_parse_stones(moves),
        komi=komi,
        board_size_x=board_size,
        board_size_y=board_size,
        analyze_turns=list(range(len(moves) + 1)),
        max_visits=max_visits,
    )

    results = await _run_query(engine, request)
    return json.dumps(results, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_mcp() -> None:
    mcp.run(transport="stdio")
