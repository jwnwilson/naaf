"""An LLMAdapter backed by headless Claude Code (`claude -p`), authed by the
user's subscription — no Anthropic API key.

Claude Code runs its own agent loop (edits/bash/tools) and returns final text,
which we capture into an LLMResponse like the API adapters do. On run *stages*
(detected by the `report` tool spec being present) we map Claude's `VERDICT:`
line into a synthesized `report` tool-call, so the existing LlmAgentRuntime's
pass/fail semantics — especially VERIFY — hold without any runtime change.
"""

import json
import os
import subprocess
from collections.abc import Callable

from adapters.agent.claude_cli.stream_runner import EventSink, streaming_runner
from domain.agent.llm import LLMMessage, LLMRequest, LLMResponse, ToolCall, Usage

_VERDICT_SUFFIX = (
    "\n\nWhen you have finished, end your reply with a single line: "
    "`VERDICT: PASS — <summary>` if the work (and any tests) succeeded, "
    "or `VERDICT: FAIL — <summary>` if it did not."
)

Runner = Callable[..., dict]


def _default_runner(argv: list[str], *, cwd=None, env=None, timeout=None) -> dict:
    try:
        proc = subprocess.run(
            argv, cwd=cwd, env=env, timeout=timeout, capture_output=True, text=True
        )
    except subprocess.TimeoutExpired:
        return {"is_error": True, "result": f"claude timed out after {timeout}s", "usage": {}}
    except FileNotFoundError:
        return {"is_error": True, "result": f"claude CLI not found ({argv[0]})", "usage": {}}
    try:
        data = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        return {
            "is_error": True,
            "result": proc.stderr or proc.stdout or f"claude exited {proc.returncode}",
            "usage": {},
        }
    if proc.returncode != 0:
        data.setdefault("is_error", True)
    return data


class ClaudeCliLLMAdapter:
    def __init__(
        self,
        *,
        claude_bin: str = "claude",
        cwd: str | None = None,
        mcp_config_path: str | None = None,
        github_token: str = "",
        claude_oauth_token: str = "",
        timeout_s: int = 900,
        runner: Runner | None = None,
    ) -> None:
        self._bin = claude_bin
        self._cwd = cwd
        self._mcp = mcp_config_path
        self._github_token = github_token
        self._claude_oauth_token = claude_oauth_token
        self._timeout = timeout_s
        self._runner: Runner | None = runner
        self._emit: EventSink | None = None

    def set_cwd(self, cwd: str) -> None:
        """Point the next `claude -p` at a directory. Wired from the runtime's
        workspace_factory so each stage runs in that stage's workspace (the
        worker is single-concurrency, so this per-stage mutation is safe)."""
        self._cwd = cwd

    def set_event_sink(self, emit: EventSink | None) -> None:
        """Attach a per-call activity sink. When set, complete() streams events
        via claude's stream-json output (single-concurrency worker → safe)."""
        self._emit = emit

    def _prompt(self, messages: list[LLMMessage]) -> str:
        return "\n\n".join(m.content for m in messages if m.content) or "(no input)"

    def _env(self) -> dict:
        env = dict(os.environ)
        env.pop("ANTHROPIC_API_KEY", None)  # force subscription auth, not a metered key
        if self._github_token:
            env["GH_TOKEN"] = self._github_token
        if self._claude_oauth_token:
            # Headless subscription auth for the container (no keychain); local
            # `make dev` leaves it unset and uses the keychain.
            env["CLAUDE_CODE_OAUTH_TOKEN"] = self._claude_oauth_token
        return env

    def complete(self, request: LLMRequest) -> LLMResponse:
        has_report = any(t.name == "report" for t in request.tools)
        system = request.system + (_VERDICT_SUFFIX if has_report else "")
        streaming = self._emit is not None
        fmt = "stream-json" if streaming else "json"
        argv = [
            self._bin, "-p", self._prompt(request.messages),
            "--output-format", fmt, "--permission-mode", "bypassPermissions",
        ]
        if streaming:
            argv += ["--verbose"]  # claude requires --verbose with stream-json under -p
        if system:
            argv += ["--append-system-prompt", system]
        if self._cwd:
            argv += ["--add-dir", self._cwd]
        if self._mcp:
            argv += ["--mcp-config", self._mcp, "--allowed-tools", "mcp__naaf__*"]

        if streaming:
            runner = self._runner or streaming_runner
            data = runner(argv, cwd=self._cwd, env=self._env(), timeout=self._timeout, emit=self._emit)
        else:
            runner = self._runner or _default_runner
            data = runner(argv, cwd=self._cwd, env=self._env(), timeout=self._timeout)

        text = str(data.get("result", ""))
        is_error = bool(data.get("is_error", False))
        u = data.get("usage") or {}
        usage = Usage(
            input_tokens=int(u.get("input_tokens", 0)),
            output_tokens=int(u.get("output_tokens", 0)),
        )

        if not has_report:
            return LLMResponse(content=text, stop_reason="end_turn", usage=usage)

        # Run stage: map Claude's verdict into the report tool-call the runtime expects.
        args: dict = {"summary": text or ("claude error" if is_error else "")}
        upper = text.upper()
        if is_error:
            args["passed"] = False
        elif "VERDICT: PASS" in upper:
            args["passed"] = True
        elif "VERDICT: FAIL" in upper:
            args["passed"] = False
        # else: omit "passed" → runtime applies its per-stage default (VERIFY fails, others pass)
        return LLMResponse(
            content=text,
            tool_calls=[ToolCall(id="report-1", name="report", args=args)],
            stop_reason="tool_use",
            usage=usage,
        )
