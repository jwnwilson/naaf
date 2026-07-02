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

## Review Fix Pass (2026-07-02)

Addressed coordinator review (2 Important + 1 Minor):

1. **(Important) Surface gateway HTTP errors** — added `resp.raise_for_status()` after the POST,
   before `body = resp.json()`. `_FakeResp` gained a no-op `raise_for_status`; added
   `test_gateway_http_error_propagates` proving a 4xx/5xx propagates instead of a cryptic
   `KeyError: 'choices'`.
2. **(Minor) Reuse the httpx client** — the lazily-built `httpx.Client` is now cached on
   `self._client`, so the worker no longer leaks a new connection pool per call.
3. **(Important) Pin the compose tag** — `docker-compose.yml` litellm image changed from the
   moving `main-latest` to `ghcr.io/berriai/litellm:main-v1.x.y  # pin a specific tag before uncommenting`.

### Commands + output

```
$ uv run pytest projects/server/tests/adapters/agent/llm/test_litellm.py -v
projects/server/tests/adapters/agent/llm/test_litellm.py ....            [100%]
4 passed in 0.02s

$ uv run pytest -m "not integration" -q
237 passed, 1 deselected in 6.72s

$ uv run ruff check .
All checks passed!
```

