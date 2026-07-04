"""Run headless Claude Code with --output-format stream-json and forward each
NDJSON event to a sink, returning the same final dict shape as _default_runner.
"""
import json
import subprocess
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
                events.append(("tool_call", {"name": block.get("name", ""), "input": block.get("input", {})}))
            elif btype == "tool_result":
                events.append(("tool_result", {"result": block.get("content", "")}))
    return events


def streaming_runner(argv, *, cwd=None, env=None, timeout=None, emit=None, _popen=subprocess.Popen) -> dict:
    result_text = ""
    is_error = False
    usage: dict = {}
    try:
        proc = _popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError:
        return {"is_error": True, "result": f"claude CLI not found ({argv[0]})", "usage": {}}
    try:
        for line in proc.stdout:  # blocks per line as claude emits them
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                obj = None
            if obj is not None and obj.get("type") == "result":
                result_text = str(obj.get("result", ""))
                is_error = bool(obj.get("is_error", False))
                usage = obj.get("usage") or {}
                continue
            if emit is not None:
                for kind, payload in parse_stream_line(line):
                    emit(kind, payload)
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        return {"is_error": True, "result": f"claude timed out after {timeout}s", "usage": {}}
    if proc.returncode not in (0, None) and not result_text:
        is_error = True
        result_text = f"claude exited {proc.returncode}"
    return {"result": result_text, "is_error": is_error, "usage": usage}
