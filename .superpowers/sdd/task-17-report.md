# Task 17 Report: LiteLLMAdapter

## Files Changed

| File | Status |
|------|--------|
| `projects/server/src/adapters/agent/llm/litellm.py` | **NEW** — LiteLLMAdapter implementation |
| `projects/server/tests/adapters/agent/llm/test_litellm.py` | **NEW** — 3 unit tests (fake client, no network) |
| `docker-compose.yml` | **MODIFIED** — litellm service added (commented out, with `# pin a specific tag` note) |
| `docs/deployment.md` | **MODIFIED** — LiteLLM gateway section added with env vars + startup instructions |

## TDD Sequence

1. Wrote test file first → import error (RED, as expected)
2. Implemented `litellm.py` → 3/3 passed (GREEN)
3. Ruff clean throughout

## Test Results

```
3 passed  — projects/server/tests/adapters/agent/llm/test_litellm.py
236 passed, 1 deselected — full suite (not integration)
Coverage: 93.65%  (gate: 80% ✓)
```

## Compose Service

Added **commented-out** `litellm` service to `docker-compose.yml` with a
`# pin a specific tag` note. Did not guess a specific `ghcr.io/berriai/litellm:main-v1.x.y`
tag — left it for the operator to pin before use, per brief instructions.

## Notes

- Factory's existing `litellm` branch (`build_llm_adapter` in `adapters/agent/factory.py`)
  now resolves cleanly — `LiteLLMAdapter(base_url=..., key=...)` constructor matches.
- `_tool_body()` in tests follows the exact OpenAI shape (`finish_reason` inside each choice,
  not at the top level) — the adapter reads `choice.get("finish_reason")` correctly.
- No new factory tests added; the factory's lazy import branch is exercised implicitly.
