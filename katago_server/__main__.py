import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="katago-server",
        description="KataGo analysis server with WebSocket and MCP interfaces",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="Start the WebSocket API server")
    serve_parser.add_argument("--host", default=None, help="Bind host (default: from config)")
    serve_parser.add_argument("--port", type=int, default=None, help="Bind port (default: from config)")
    serve_parser.add_argument("--log-level", default=None, help="Log level (default: from config)")

    subparsers.add_parser("mcp", help="Start the MCP stdio server")

    args = parser.parse_args()

    if args.command == "serve":
        from katago_server.serve import run_server

        run_server(host=args.host, port=args.port, log_level=args.log_level)

    elif args.command == "mcp":
        print("MCP server not yet implemented.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
