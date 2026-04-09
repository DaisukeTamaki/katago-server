"""FastAPI WebSocket server for real-time KataGo analysis."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from katago_server.config import Settings, settings
from katago_server.engine import KataGoEngine
from katago_server.models import (
    AnalysisRequest,
    TerminateRequest,
    build_katago_query,
    build_terminate_query,
)

logger = logging.getLogger(__name__)

engine: KataGoEngine | None = None


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    global engine
    engine = KataGoEngine(settings)
    await engine.start()
    try:
        yield
    finally:
        await engine.stop()
        engine = None


def create_app(app_settings: Settings | None = None) -> FastAPI:
    s = app_settings or settings

    app = FastAPI(
        title="katago-server",
        version="0.1.0",
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health_check() -> JSONResponse:
        running = engine is not None and engine.is_running
        status = "ok" if running else "unavailable"
        code = 200 if running else 503
        return JSONResponse(status_code=code, content={"status": status})

    @app.websocket("/ws/analyze")
    async def websocket_analyze(websocket: WebSocket) -> None:
        await websocket.accept()
        assert engine is not None

        async def send_response(response: dict) -> None:
            await websocket.send_json(response)

        try:
            while True:
                data = await websocket.receive_json()

                if data.get("action") in ("terminate", "terminate_all"):
                    req = TerminateRequest(
                        id=data["id"],
                        action=data["action"],
                        terminate_id=data.get("terminateId", data.get("terminate_id", "")),
                        turn_numbers=data.get("turnNumbers", data.get("turn_numbers")),
                    )
                    await engine.submit_terminate(build_terminate_query(req))
                else:
                    req = _parse_analysis_request(data, s)
                    query = build_katago_query(req)
                    await engine.submit_query(query, send_response)

        except WebSocketDisconnect:
            logger.info("Client disconnected")
            engine.remove_queries_for_callback(send_response)

    return app


def _parse_analysis_request(data: dict, s: Settings) -> AnalysisRequest:
    """Build an AnalysisRequest from raw client JSON, applying server defaults."""
    stones_key = "initial_stones" if "initial_stones" in data else "initialStones"
    initial_stones_raw = data.get(stones_key, [])
    moves_raw = data.get("moves", [])

    from katago_server.models import StonePosition

    def parse_stones(raw: list) -> list[StonePosition]:
        return [
            StonePosition(color=s["color"], position=tuple(s["position"]))
            if isinstance(s, dict)
            else s
            for s in raw
        ]

    return AnalysisRequest(
        id=data["id"],
        moves=parse_stones(moves_raw),
        initial_stones=parse_stones(initial_stones_raw),
        initial_player=data.get("initial_player") or data.get("initialPlayer"),
        rules=data.get("rules", s.default_rules),
        komi=data.get("komi", s.default_komi),
        board_size_x=data.get("board_size_x", data.get("boardXSize", s.board_size_x)),
        board_size_y=data.get("board_size_y", data.get("boardYSize", s.board_size_y)),
        analyze_turns=data.get("analyze_turns", data.get("analyzeTurns", [])),
        max_visits=data.get("max_visits", data.get("maxVisits")),
        report_during_search_every=data.get(
            "report_during_search_every",
            data.get("reportDuringSearchEvery", s.report_during_search_every),
        ),
        include_ownership=data.get("include_ownership", data.get("includeOwnership", False)),
        include_ownership_stdev=data.get(
            "include_ownership_stdev", data.get("includeOwnershipStdev", False)
        ),
        include_policy=data.get("include_policy", data.get("includePolicy", False)),
        include_pv_visits=data.get("include_pv_visits", data.get("includePVVisits", False)),
        override_settings=data.get("override_settings", data.get("overrideSettings")),
        priority=data.get("priority"),
    )


def run_server(
    host: str | None = None,
    port: int | None = None,
    log_level: str | None = None,
) -> None:
    app = create_app()
    uvicorn.run(
        app,
        host=host or settings.host,
        port=port or settings.port,
        log_level=log_level or settings.log_level,
    )
