from __future__ import annotations

from fastapi.testclient import TestClient

from katago_server.config import Settings
from katago_server.serve import _parse_analysis_request, create_app


class FakeEngine:
    instances: list[FakeEngine] = []

    def __init__(self, _settings: Settings) -> None:
        self.is_running = False
        self.submitted_queries: list[dict] = []
        self.submitted_terminations: list[dict] = []
        self.removed_callbacks = 0
        self.__class__.instances.append(self)

    async def start(self) -> None:
        self.is_running = True

    async def stop(self) -> None:
        self.is_running = False

    async def submit_query(self, query: dict, callback) -> None:  # noqa: ANN001
        self.submitted_queries.append(query)
        await callback(
            {
                "id": query["id"],
                "turnNumber": 0,
                "isDuringSearch": False,
                "moveInfos": [],
                "rootInfo": {
                    "currentPlayer": "b",
                    "winrate": 0.5,
                    "scoreLead": 0.0,
                    "scoreSelfplay": 0.0,
                    "utility": 0.0,
                    "visits": 10,
                    "thisHash": "hash-a",
                    "symHash": "hash-b",
                },
            }
        )

    async def submit_terminate(self, query: dict) -> None:
        self.submitted_terminations.append(query)

    def remove_queries_for_callback(self, _callback) -> None:  # noqa: ANN001
        self.removed_callbacks += 1


def test_parse_analysis_request_accepts_snake_case() -> None:
    settings = Settings()
    request = _parse_analysis_request(
        {
            "id": "query-1",
            "moves": [{"color": "b", "position": [3, 3]}],
            "initial_stones": [{"color": "w", "position": [15, 15]}],
            "initial_player": "b",
            "board_size_x": 13,
            "board_size_y": 13,
            "analyze_turns": [0, 1],
            "max_visits": 200,
            "include_policy": True,
        },
        settings,
    )

    assert request.id == "query-1"
    assert request.moves[0].position == (3, 3)
    assert request.initial_stones[0].position == (15, 15)
    assert request.initial_player == "b"
    assert request.board_size_x == 13
    assert request.analyze_turns == [0, 1]
    assert request.max_visits == 200
    assert request.include_policy is True


def test_parse_analysis_request_accepts_camel_case() -> None:
    settings = Settings()
    request = _parse_analysis_request(
        {
            "id": "query-2",
            "moves": [{"color": "b", "position": [4, 4]}],
            "initialStones": [{"color": "w", "position": [16, 16]}],
            "initialPlayer": "w",
            "boardXSize": 9,
            "boardYSize": 9,
            "analyzeTurns": [0],
            "maxVisits": 300,
            "includeOwnership": True,
        },
        settings,
    )

    assert request.id == "query-2"
    assert request.initial_stones[0].position == (16, 16)
    assert request.initial_player == "w"
    assert request.board_size_x == 9
    assert request.analyze_turns == [0]
    assert request.max_visits == 300
    assert request.include_ownership is True


def test_health_endpoint_uses_engine_status(monkeypatch) -> None:  # noqa: ANN001
    FakeEngine.instances.clear()
    monkeypatch.setattr("katago_server.serve.KataGoEngine", FakeEngine)
    app = create_app(Settings())

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_websocket_analyze_and_terminate(monkeypatch) -> None:  # noqa: ANN001
    FakeEngine.instances.clear()
    monkeypatch.setattr("katago_server.serve.KataGoEngine", FakeEngine)
    app = create_app(Settings())

    with TestClient(app) as client:
        with client.websocket_connect("/ws/analyze") as websocket:
            websocket.send_json(
                {
                    "id": "query-1",
                    "moves": [{"color": "b", "position": [3, 3]}],
                    "analyze_turns": [0],
                }
            )
            response = websocket.receive_json()
            assert response["id"] == "query-1"
            assert response["isDuringSearch"] is False

            websocket.send_json(
                {
                    "id": "cancel-1",
                    "action": "terminate",
                    "terminate_id": "query-1",
                }
            )

    engine = FakeEngine.instances[0]
    assert engine.submitted_queries[0]["id"] == "query-1"
    assert engine.submitted_terminations[0]["terminateId"] == "query-1"
    assert engine.removed_callbacks == 1
