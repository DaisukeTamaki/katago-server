"""Data types aligned with the KataGo Analysis Engine protocol.

Reference: https://github.com/lightvector/KataGo/blob/master/docs/Analysis_Engine.md
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

GTP_COLUMNS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"


def position_to_gtp(row: int, col: int) -> str:
    """Convert (row, col) to GTP coordinate string (e.g. 'D4').

    GTP uses letters A-T (skipping I) for columns, 1-19 for rows.
    Row 0 is the bottom of the board (row 1 in GTP).
    """
    return f"{GTP_COLUMNS[col]}{row + 1}"


def gtp_to_position(gtp: str) -> tuple[int, int]:
    """Convert GTP coordinate string (e.g. 'D4') to (row, col)."""
    if gtp.lower() == "pass":
        return (-1, -1)
    col = GTP_COLUMNS.index(gtp[0].upper())
    row = int(gtp[1:]) - 1
    return (row, col)


# ---------------------------------------------------------------------------
# Inbound: client -> katago-server
# ---------------------------------------------------------------------------


class StonePosition(BaseModel):
    color: str = Field(description="'b' or 'w'")
    position: tuple[int, int] = Field(description="(row, col), 0-indexed from bottom-left")


class AvoidMovesSpec(BaseModel):
    player: str
    moves: list[str]
    until_depth: int = Field(alias="untilDepth")


class AnalysisRequest(BaseModel):
    """Client request for position analysis.

    Fields mirror KataGo's query format but use snake_case.
    `build_katago_query()` converts to the wire format KataGo expects.
    """

    id: str
    moves: list[StonePosition] = Field(default_factory=list)
    initial_stones: list[StonePosition] = Field(default_factory=list)
    initial_player: str | None = None
    rules: str = "tromp-taylor"
    komi: float = 6.5
    board_size_x: int = 19
    board_size_y: int = 19
    analyze_turns: list[int] = Field(default_factory=list)
    max_visits: int | None = None
    report_during_search_every: float | None = None

    include_ownership: bool = False
    include_ownership_stdev: bool = False
    include_policy: bool = False
    include_pv_visits: bool = False

    avoid_moves: list[AvoidMovesSpec] | None = None
    allow_moves: list[AvoidMovesSpec] | None = None

    override_settings: dict[str, Any] | None = None
    priority: int | None = None


class TerminateRequest(BaseModel):
    id: str
    action: str = "terminate"
    terminate_id: str
    turn_numbers: list[int] | None = None


# ---------------------------------------------------------------------------
# Outbound: KataGo -> client  (for type-checking / documentation)
# ---------------------------------------------------------------------------


class MoveAnalysis(BaseModel, extra="allow"):
    """Per-move analysis from KataGo's moveInfos array."""

    move: str
    visits: int
    winrate: float
    score_lead: float = Field(alias="scoreLead")
    score_mean: float = Field(alias="scoreMean")
    score_stdev: float = Field(alias="scoreStdev")
    prior: float
    utility: float
    lcb: float
    order: int
    pv: list[str] = Field(default_factory=list)
    human_prior: float | None = Field(default=None, alias="humanPrior")


class RootInfo(BaseModel, extra="allow"):
    """Root position info from KataGo's rootInfo object."""

    current_player: str = Field(alias="currentPlayer")
    winrate: float
    score_lead: float = Field(alias="scoreLead")
    score_selfplay: float = Field(alias="scoreSelfplay")
    utility: float
    visits: int
    this_hash: str = Field(alias="thisHash")
    sym_hash: str = Field(alias="symHash")


class AnalysisResponse(BaseModel, extra="allow"):
    """A single analysis result from KataGo."""

    id: str
    turn_number: int = Field(alias="turnNumber")
    is_during_search: bool = Field(alias="isDuringSearch")
    move_infos: list[MoveAnalysis] | None = Field(default=None, alias="moveInfos")
    root_info: RootInfo | None = Field(default=None, alias="rootInfo")
    ownership: list[float] | None = None
    policy: list[float] | None = None
    no_results: bool | None = Field(default=None, alias="noResults")


# ---------------------------------------------------------------------------
# Query builders: AnalysisRequest -> KataGo JSON
# ---------------------------------------------------------------------------


def build_katago_query(request: AnalysisRequest) -> dict[str, Any]:
    """Transform an AnalysisRequest into the JSON dict KataGo expects on stdin."""
    query: dict[str, Any] = {
        "id": request.id,
        "moves": [
            [m.color, position_to_gtp(*m.position)] for m in request.moves
        ],
        "initialStones": [
            [s.color, position_to_gtp(*s.position)] for s in request.initial_stones
        ],
        "rules": request.rules,
        "komi": request.komi,
        "boardXSize": request.board_size_x,
        "boardYSize": request.board_size_y,
    }

    if request.initial_player is not None:
        query["initialPlayer"] = request.initial_player
    if request.analyze_turns:
        query["analyzeTurns"] = request.analyze_turns
    if request.max_visits is not None:
        query["maxVisits"] = request.max_visits
    if request.report_during_search_every is not None:
        query["reportDuringSearchEvery"] = request.report_during_search_every
    if request.include_ownership:
        query["includeOwnership"] = True
    if request.include_ownership_stdev:
        query["includeOwnershipStdev"] = True
    if request.include_policy:
        query["includePolicy"] = True
    if request.include_pv_visits:
        query["includePVVisits"] = True
    if request.avoid_moves is not None:
        query["avoidMoves"] = [
            {"player": a.player, "moves": a.moves, "untilDepth": a.until_depth}
            for a in request.avoid_moves
        ]
    if request.allow_moves is not None:
        query["allowMoves"] = [
            {"player": a.player, "moves": a.moves, "untilDepth": a.until_depth}
            for a in request.allow_moves
        ]
    if request.override_settings is not None:
        query["overrideSettings"] = request.override_settings
    if request.priority is not None:
        query["priority"] = request.priority

    return query


def build_terminate_query(request: TerminateRequest) -> dict[str, Any]:
    """Transform a TerminateRequest into the JSON dict KataGo expects."""
    query: dict[str, Any] = {
        "id": request.id,
        "action": request.action,
        "terminateId": request.terminate_id,
    }
    if request.turn_numbers is not None:
        query["turnNumbers"] = request.turn_numbers
    return query
