"""Run headless Claude Code with --output-format stream-json and forward each
NDJSON event to a sink, returning the same final dict shape as _default_runner.
"""
import json
import queue
import subprocess
import threading
import time
from collections.abc import Callable

EventSink = Callable[[str, dict], None]


def parse_stream_line(line: str) -> list[tuple[str, dict]]:
    """Map one NDJSON line to zero+ (kind, payload) events. The terminal
    ``result`` line returns [] — the runner assembles the final dict from it."""
    line = line.strip()
    if not line:
        return []
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return []
    kind = obj.get("type")
    events: list[tuple[str, dict]] = []
    if kind in ("assistant", "user"):
        for block in obj.get("message", {}).get("content", []):
            btype = block.get("type")
            if btype == "text" and block.get("text"):
                events.append(("text_block", {"text": block["text"]}))
            elif btype == "tool_use":
                events.append((
                    "tool_call",
                    {"name": block.get("name", ""), "input": block.get("input", {})},
                ))
            elif btype == "tool_result":
                events.append(("tool_result", {"result": block.get("content", "")}))
    return events


def streaming_runner(
    argv, *, cwd=None, env=None, timeout=None, emit=None, _popen=subprocess.Popen
) -> dict:
    result_text = ""
    is_error = False
    usage: dict = {}
    try:
        proc = _popen(
            argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
    except FileNotFoundError:
        return {"is_error": True, "result": f"claude CLI not found ({argv[0]})", "usage": {}}

    # Drain stdout in a daemon thread and consume via a queue so the wall-clock
    # timeout is enforced even if claude hangs mid-stream with the pipe open
    # (a blocking readline would otherwise defeat `timeout`).
    lines: queue.Queue = queue.Queue()
    _EOF = object()

    def _drain() -> None:
        try:
            for ln in proc.stdout:
                lines.put(ln)
        finally:
            lines.put(_EOF)

    threading.Thread(target=_drain, daemon=True).start()

    # In production the adapter always passes a real timeout (claude_timeout_s); the
    # timeout=None branch (unbounded lines.get()) is only reached by callers that opt
    # out, and still terminates for any finite stream (the drain thread queues _EOF).
    deadline = None if timeout is None else time.monotonic() + timeout

    def _timed_out() -> dict:
        proc.kill()
        try:  # reap the killed child so it doesn't linger as a zombie
            proc.wait(timeout=1)
        except Exception:
            pass
        return {"is_error": True, "result": f"claude timed out after {timeout}s", "usage": {}}

    while True:
        if deadline is None:
            item = lines.get()
        else:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return _timed_out()
            try:
                item = lines.get(timeout=remaining)
            except queue.Empty:
                return _timed_out()
        if item is _EOF:
            break
        try:
            obj = json.loads(item)
        except (json.JSONDecodeError, ValueError):
            obj = None
        if obj is not None and obj.get("type") == "result":
            result_text = str(obj.get("result", ""))
            is_error = bool(obj.get("is_error", False))
            usage = obj.get("usage") or {}
            continue
        if emit is not None:
            for kind, payload in parse_stream_line(item):
                emit(kind, payload)

    proc.wait()
    if proc.returncode not in (0, None) and not result_text:
        is_error = True
        result_text = f"claude exited {proc.returncode}"
    return {"result": result_text, "is_error": is_error, "usage": usage}
