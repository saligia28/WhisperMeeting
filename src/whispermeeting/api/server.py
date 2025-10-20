"""Development server launcher with auto-incrementing port support."""

from __future__ import annotations

import argparse
import os
import socket
from contextlib import closing

import uvicorn


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run WhisperMeeting API server.")
    default_host = os.getenv("WHISPERMEETING_HOST", "127.0.0.1")
    default_port = int(os.getenv("WHISPERMEETING_PORT", "8000"))
    default_limit = int(os.getenv("WHISPERMEETING_PORT_SEARCH_LIMIT", "20"))

    parser.add_argument("--host", default=default_host, help="Host interface to bind.")
    parser.add_argument(
        "--port",
        type=int,
        default=default_port,
        help="Starting port to try. Falls back to a higher port if occupied.",
    )
    parser.add_argument(
        "--port-search-limit",
        type=int,
        default=default_limit,
        help="How many consecutive ports to probe when looking for a free one.",
    )
    parser.add_argument(
        "--reload",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable auto-reload in development (default: on).",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("WHISPERMEETING_LOG_LEVEL", "info"),
        help="Uvicorn log level.",
    )
    return parser.parse_args(argv)


def _is_port_available(host: str, port: int) -> bool:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _find_available_port(host: str, start_port: int, search_limit: int) -> int:
    for offset in range(search_limit):
        candidate = start_port + offset
        if _is_port_available(host, candidate):
            return candidate
    raise RuntimeError(
        f"No free port found in range [{start_port}, {start_port + search_limit - 1}]."
    )


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    port = _find_available_port(args.host, args.port, args.port_search_limit)
    if port != args.port:
        print(
            f"[whispermeeting] Port {args.port} is busy; falling back to {port}.",
            flush=True,
        )

    uvicorn.run(
        "whispermeeting.api.app:app",
        host=args.host,
        port=port,
        reload=args.reload,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
