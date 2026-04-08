"""KataGo subprocess manager.

Handles process lifecycle, stdin/stdout JSON-line communication,
and routing of asynchronous responses back to callers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from katago_server.config import Settings

logger = logging.getLogger(__name__)

ResponseCallback = Callable[[dict], Awaitable[None]]


@dataclass
class _QueryTracker:
    """Internal state for an in-flight analysis query."""

    callback: ResponseCallback
    pending_turns: set[int] = field(default_factory=set)


class KataGoEngine:
    """Manages a single KataGo analysis subprocess.

    Usage::

        engine = KataGoEngine(settings)
        await engine.start()
        # ... submit queries ...
        await engine.stop()

    Or as an async context manager::

        async with KataGoEngine(settings) as engine:
            ...
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._process: subprocess.Popen[str] | None = None
        self._queries: dict[str, _QueryTracker] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._started = asyncio.Event()

    async def __aenter__(self) -> KataGoEngine:
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.stop()

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        if self._process is not None:
            return

        cmd = [
            str(self._settings.katago_binary),
            "analysis",
            "-config", str(self._settings.analysis_config),
            "-model", str(self._settings.model_path),
        ]
        if self._settings.human_model_path is not None:
            cmd += ["-human-model", str(self._settings.human_model_path)]
        logger.info("Starting KataGo: %s", " ".join(cmd))

        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._reader_task = asyncio.create_task(self._read_responses(), name="katago-reader")
        self._stderr_task = asyncio.create_task(self._read_stderr(), name="katago-stderr")
        self._started.set()

    async def stop(self) -> None:
        if self._process is None:
            return

        logger.info("Stopping KataGo (pid=%d)", self._process.pid)

        if self._process.stdin and not self._process.stdin.closed:
            self._process.stdin.close()

        try:
            self._process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            logger.warning("KataGo did not exit in time, killing")
            self._process.kill()
            self._process.wait()

        for task in (self._reader_task, self._stderr_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self._process = None
        self._queries.clear()
        self._started.clear()
        logger.info("KataGo stopped")

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    # -- query submission ----------------------------------------------------

    async def submit_query(
        self,
        query: dict,
        callback: ResponseCallback,
    ) -> None:
        """Send an analysis query to KataGo.

        Each response (partial or final) is delivered via *callback*.
        The tracker is automatically cleaned up when all requested turns
        have received their final (non-isDuringSearch) response.
        """
        self._assert_running()

        query_id = query["id"]
        analyze_turns = query.get("analyzeTurns", [])

        self._queries[query_id] = _QueryTracker(
            callback=callback,
            pending_turns=set(analyze_turns) if analyze_turns else set(),
        )

        self._write(query)

    async def submit_terminate(self, query: dict) -> None:
        """Send a terminate or terminate_all action to KataGo."""
        self._assert_running()
        self._write(query)

    def remove_queries_for_callback(self, callback: ResponseCallback) -> None:
        """Remove all tracked queries associated with a given callback.

        Called when a WebSocket client disconnects so we stop routing
        responses to a dead connection.
        """
        to_remove = [
            qid for qid, tracker in self._queries.items()
            if tracker.callback is callback
        ]
        for qid in to_remove:
            del self._queries[qid]

    # -- internals -----------------------------------------------------------

    def _assert_running(self) -> None:
        if not self.is_running:
            raise RuntimeError("KataGo process is not running")

    def _write(self, payload: dict) -> None:
        assert self._process is not None and self._process.stdin is not None
        line = json.dumps(payload) + "\n"
        self._process.stdin.write(line)
        self._process.stdin.flush()

    async def _read_responses(self) -> None:
        assert self._process is not None and self._process.stdout is not None

        while True:
            if self._process.poll() is not None:
                logger.error("KataGo exited unexpectedly (code=%s)", self._process.returncode)
                break

            line = await asyncio.to_thread(self._process.stdout.readline)
            if not line:
                logger.info("KataGo stdout closed")
                break

            try:
                response = json.loads(line)
            except json.JSONDecodeError:
                logger.error("Invalid JSON from KataGo: %s", line.strip())
                continue

            await self._dispatch_response(response)

    async def _dispatch_response(self, response: dict) -> None:
        query_id = response.get("id")
        if query_id is None:
            if "error" in response:
                logger.error("KataGo error (no query id): %s", response["error"])
            return

        tracker = self._queries.get(query_id)
        if tracker is None:
            logger.debug("Response for unknown/completed query %s, ignoring", query_id)
            return

        try:
            await tracker.callback(response)
        except Exception:
            logger.exception("Callback failed for query %s", query_id)
            self._queries.pop(query_id, None)
            return

        is_during_search = response.get("isDuringSearch", False)
        if is_during_search:
            return

        turn_number = response.get("turnNumber")
        no_results = response.get("noResults", False)

        if no_results or turn_number is not None:
            tracker.pending_turns.discard(turn_number)

        if not tracker.pending_turns:
            del self._queries[query_id]
            logger.debug("Query %s completed", query_id)

    async def _read_stderr(self) -> None:
        assert self._process is not None and self._process.stderr is not None

        while True:
            line = await asyncio.to_thread(self._process.stderr.readline)
            if not line:
                break
            logger.info("KataGo: %s", line.rstrip())
