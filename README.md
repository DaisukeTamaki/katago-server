# katago-server

A standalone [KataGo](https://github.com/lightvector/KataGo) analysis server with two interfaces:

- **WebSocket API** for real-time board interaction (game UIs, analysis tools)
- **MCP server** for LLM tool calls (Claude Desktop, Cursor, custom agents)

Both interfaces share a single KataGo process, so you only need one GPU.

## Quick Start

### Prerequisites

- Python 3.11+
- KataGo binary ([build instructions](https://github.com/lightvector/KataGo#compiling-katago) or [releases](https://github.com/lightvector/KataGo/releases))
- A KataGo model file (download from [KataGo releases](https://github.com/lightvector/KataGo/releases))

### Install

```bash
pip install -e .
```

### Run the WebSocket server

```bash
# Set paths via environment variables
export KATAGO_KATAGO_BINARY=katago
export KATAGO_ANALYSIS_CONFIG=config/analysis.cfg
export KATAGO_MODEL_PATH=/path/to/model.bin.gz

katago-server serve
```

The server starts on `http://localhost:8000` with:
- `GET /health` -- health check
- `WS /ws/analyze` -- analysis WebSocket

### Run the MCP server

```bash
katago-server mcp
```

Communicates over stdio using the [Model Context Protocol](https://modelcontextprotocol.io/).

## Docker

```bash
# Requires NVIDIA Container Toolkit for GPU access
docker compose up
```

See the [Dockerfile](Dockerfile) for details. The image builds KataGo from source with TensorRT support.

## WebSocket API

Connect to `ws://localhost:8000/ws/analyze` and exchange JSON messages.

### Analyze a position

Send:

```json
{
  "id": "query-1",
  "moves": [
    {"color": "b", "position": [3, 3]},
    {"color": "w", "position": [15, 15]},
    {"color": "b", "position": [3, 15]}
  ],
  "komi": 6.5,
  "analyze_turns": [0, 1, 2, 3],
  "max_visits": 500,
  "include_policy": true
}
```

Positions are `[row, col]`, 0-indexed from the bottom-left of the board.

The server streams partial results (with `isDuringSearch: true`) and a final result for each requested turn. See the [KataGo Analysis Engine docs](https://github.com/lightvector/KataGo/blob/master/docs/Analysis_Engine.md) for the full response format.

### Analyze with initial stones (no move history)

For positions without move history (e.g., from a board photo):

```json
{
  "id": "query-2",
  "initial_stones": [
    {"color": "b", "position": [3, 3]},
    {"color": "w", "position": [15, 15]}
  ],
  "initial_player": "b",
  "komi": 6.5
}
```

### Human-level analysis

Use `override_settings` to configure KataGo's human SL model. This requires running KataGo with a `-human-model` argument.

```json
{
  "id": "query-3",
  "moves": [{"color": "b", "position": [3, 3]}],
  "komi": 6.5,
  "include_policy": true,
  "override_settings": {
    "humanSLProfile": "rank_5k",
    "ignorePreRootHistory": false
  }
}
```

The response will include `humanPrior` on each move and `humanWinrate` / `humanScoreMean` on the root info.

### Terminate a query

```json
{
  "id": "cancel-1",
  "action": "terminate",
  "terminate_id": "query-1"
}
```

## MCP Tools

When running as an MCP server, the following tools are available:

| Tool | Description |
|------|-------------|
| `analyze_position` | Analyze a board position, returning best moves with win rates, scores, and principal variations |
| `analyze_human_move` | Predict what a human at a given rank would play, plus the gap from optimal |
| `compare_moves` | Compare two moves by evaluating both continuations |
| `evaluate_variation` | Evaluate a sequence of moves, returning analysis at each step |

### MCP client configuration

For Claude Desktop, add to your config:

```json
{
  "mcpServers": {
    "katago": {
      "command": "katago-server",
      "args": ["mcp"],
      "env": {
        "KATAGO_KATAGO_BINARY": "katago",
        "KATAGO_MODEL_PATH": "/path/to/model.bin.gz",
        "KATAGO_ANALYSIS_CONFIG": "/path/to/analysis.cfg"
      }
    }
  }
}
```

## Configuration

All settings can be configured via environment variables with the `KATAGO_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `KATAGO_KATAGO_BINARY` | `katago` | Path to KataGo executable |
| `KATAGO_ANALYSIS_CONFIG` | `config/analysis.cfg` | Path to KataGo analysis config |
| `KATAGO_MODEL_PATH` | `models/default.bin.gz` | Path to neural network model |
| `KATAGO_HOST` | `0.0.0.0` | Server bind host |
| `KATAGO_PORT` | `8000` | Server bind port |
| `KATAGO_DEFAULT_KOMI` | `6.5` | Default komi |
| `KATAGO_DEFAULT_RULES` | `tromp-taylor` | Default ruleset |
| `KATAGO_REPORT_DURING_SEARCH_EVERY` | `0.2` | Seconds between partial results |

## License

MIT
