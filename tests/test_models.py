from katago_server.models import (
    AnalysisRequest,
    TerminateRequest,
    build_katago_query,
    build_terminate_query,
    gtp_to_position,
    position_to_gtp,
)


def test_position_to_gtp_skips_i_column() -> None:
    assert position_to_gtp(0, 0) == "A1"
    assert position_to_gtp(3, 7) == "H4"
    assert position_to_gtp(3, 8) == "J4"


def test_gtp_to_position_handles_pass_and_round_trip() -> None:
    assert gtp_to_position("pass") == (-1, -1)
    assert gtp_to_position("J4") == (3, 8)
    assert gtp_to_position(position_to_gtp(15, 15)) == (15, 15)


def test_build_katago_query_includes_optional_fields() -> None:
    request = AnalysisRequest(
        id="query-1",
        moves=[{"color": "b", "position": (3, 3)}],
        initial_stones=[{"color": "w", "position": (15, 15)}],
        initial_player="b",
        rules="japanese",
        komi=7.5,
        board_size_x=19,
        board_size_y=19,
        analyze_turns=[0, 1],
        max_visits=500,
        report_during_search_every=0.1,
        include_ownership=True,
        include_ownership_stdev=True,
        include_policy=True,
        include_pv_visits=True,
        avoid_moves=[{"player": "b", "moves": ["D4"], "untilDepth": 3}],
        allow_moves=[{"player": "w", "moves": ["Q16"], "untilDepth": 2}],
        override_settings={"humanSLProfile": "rank_5k"},
        priority=10,
    )

    query = build_katago_query(request)

    assert query["id"] == "query-1"
    assert query["moves"] == [["b", "D4"]]
    assert query["initialStones"] == [["w", "Q16"]]
    assert query["initialPlayer"] == "b"
    assert query["rules"] == "japanese"
    assert query["komi"] == 7.5
    assert query["analyzeTurns"] == [0, 1]
    assert query["maxVisits"] == 500
    assert query["reportDuringSearchEvery"] == 0.1
    assert query["includeOwnership"] is True
    assert query["includeOwnershipStdev"] is True
    assert query["includePolicy"] is True
    assert query["includePVVisits"] is True
    assert query["avoidMoves"] == [{"player": "b", "moves": ["D4"], "untilDepth": 3}]
    assert query["allowMoves"] == [{"player": "w", "moves": ["Q16"], "untilDepth": 2}]
    assert query["overrideSettings"] == {"humanSLProfile": "rank_5k"}
    assert query["priority"] == 10


def test_build_terminate_query_with_turn_numbers() -> None:
    request = TerminateRequest(
        id="cancel-1",
        terminate_id="query-1",
        turn_numbers=[3, 4],
    )

    query = build_terminate_query(request)

    assert query == {
        "id": "cancel-1",
        "action": "terminate",
        "terminateId": "query-1",
        "turnNumbers": [3, 4],
    }
