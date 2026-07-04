# Claude Code in the Worker + Subscription Auth — Design

> Make the **containerized** worker able to run agents on the Claude subscription via `claude -p`:
> install Claude Code in the worker image and authenticate it with a **per-owner secret** injected
> per run. Builds on the Claude CLI runtime + MCP server (PR #48).

## Problem

The `claude_cli` runtime (PR #48) works for the **local** `make dev` worker — it spawns the host's
`claude`, which is authed via the user's keychain. The **containerized** worker (`Dockerfile`:
python-slim + git + gh + uv; `docker-compose.yml` `worker` service) has **neither** the `claude`
binary **nor** any subscription auth (the keychain isn't available in a container). So a run in the
container fails: `claude` not found / not authenticated.

## Decision (resolved during brainstorming)

Authenticate via a **per-owner secret** (`claude_oauth_token`, from `claude setup-token`) stored in
**Settings → Secrets** and injected as `CLAUDE_CODE_OAUTH_TOKEN` into each `claude -p` subprocess —
mirroring `github_token → GH_TOKEN`. This reuses the encrypted secrets feature, works for both the
local and containerized worker, is per-owner, and keeps the token out of `.env`. The local worker
still falls back to the keychain when the secret is unset.

## 1. Install Claude Code in the worker image (`Dockerfile`)

Add the **native installer** (no Node.js) after the `gh` install:

```dockerfile
# Claude Code CLI (native installer; used by naaf_llm_provider=claude_cli)
RUN curl -fsSL https://claude.ai/install.sh | bash \
 && ln -sf /root/.local/bin/claude /usr/local/bin/claude \
 && claude --version
```

The symlink puts `claude` on the worker process's `PATH` (`/usr/local/bin`); `claude --version` fails
the build if the install broke. `naaf_claude_bin` remains an absolute-path escape hatch.

## 2. Auth as a per-owner secret

- **Allowlist** (`domain/secrets/secret.py`): add `claude_oauth_token` to `SECRET_NAMES` →
  `("anthropic_api_key", "github_token", "claude_oauth_token")`. The write-only secrets API accepts
  it automatically (validates against `SECRET_NAMES`).
- **Resolver** (`adapters/agent/secrets_resolver.py`): add
  `claude_oauth_token() -> str` = stored value, else `os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")`.
- **Adapter** (`ClaudeCliLLMAdapter`): accept a `claude_oauth_token` param; `_env()` sets
  `CLAUDE_CODE_OAUTH_TOKEN` when non-empty (alongside `GH_TOKEN`; still pops `ANTHROPIC_API_KEY`).
  When empty, it sets nothing → the local worker uses the keychain unchanged.
- **Wiring** (`factory.build_claude_cli_deps` / `build_agent_deps` / `ctx_factory`): resolve the
  token via `SecretResolver.claude_oauth_token()` and pass it to the adapter (same path as
  `github_token`).
- **UI** (`modules/settings/SecretsPanel.tsx`): add a third field — **Claude subscription token**
  (`name: "claude_oauth_token"`, placeholder "from `claude setup-token`") — to the existing masked
  Set/Not-set form. No other UI change (the write-only API + hooks already generalize over names).

## 3. Compose wiring (`docker-compose.yml` worker service)

Add to the `worker` service `environment`:
- `naaf_llm_provider: ${naaf_llm_provider:-}` — select `claude_cli` at run.
- `naaf_secret_key: ${naaf_secret_key:-}` — the container must **decrypt** the stored token.

No auth token in compose/`.env` — it lives in the encrypted store, injected per run. The MCP server
the adapter spawns (`python -m interactors.mcp.server`) already receives `naaf_db_url`
(→ `postgres:5432`) via the generated mcp-config, so it reaches Postgres from inside the container.

## Data flow

```
run stage (container worker, naaf_llm_provider=claude_cli):
  ctx_factory → SecretResolver.claude_oauth_token()/github_token()
    → ClaudeCliLLMAdapter(claude_oauth_token, github_token, mcp_config)
    → subprocess `claude -p` with env {CLAUDE_CODE_OAUTH_TOKEN, GH_TOKEN} (ANTHROPIC_API_KEY popped)
      → Claude Code authed by the subscription token; edits/tests/PR + naaf MCP tools
```

## Error handling

- No stored token **and** no `CLAUDE_CODE_OAUTH_TOKEN` env **and** no keychain (container) →
  `claude -p` returns an auth error; the adapter maps it to a failed stage (halts the run) with the
  error surfaced in the summary — not a worker crash.
- `naaf_secret_key` unset in the container → the token can't be decrypted → resolver returns the env
  fallback (or empty); the run fails fast with the auth error above. (Documented.)
- Image-build failure if the Claude install breaks (`claude --version` gate).

## Testing

- **Unit:** `SECRET_NAMES` includes `claude_oauth_token`; `SecretResolver.claude_oauth_token()`
  prefers stored over env and falls back when unset; `ClaudeCliLLMAdapter` sets
  `CLAUDE_CODE_OAUTH_TOKEN` in the subprocess env when provided and omits it when not;
  `build_claude_cli_deps` threads the token through; the secrets API accepts a PUT to
  `claude_oauth_token` and rejects unknown names (existing test extends).
- **UI:** `SecretsPanel` renders the third field; save/clear works (existing panel test extends).
- **Not unit-testable:** the Dockerfile install + in-container `claude` auth — validated by building
  the worker image (`docker compose build worker` → `claude --version`) and a live containerized run
  (dogfood). Called out explicitly.
- Gates: `make coverage` (80%) + `make lint` green.

## Non-goals

No GitHub App per-run tokens; no sandbox (bypassPermissions still runs freely in the workspace); no
Node-based Claude install; the OAuth token is stored encrypted + write-only like the other secrets.
Local `make dev` keychain auth is unchanged. **Depends on PR #48.**

## Files (summary)

| File | Change |
|------|--------|
| `Dockerfile` | install Claude Code (native) + symlink + version gate |
| `docker-compose.yml` | worker env: `naaf_llm_provider`, `naaf_secret_key` |
| `projects/server/src/domain/secrets/secret.py` | add `claude_oauth_token` to `SECRET_NAMES` |
| `.../adapters/agent/secrets_resolver.py` | `claude_oauth_token()` |
| `.../adapters/agent/claude_cli/adapter.py` | inject `CLAUDE_CODE_OAUTH_TOKEN` |
| `.../adapters/agent/factory.py` | thread the token through `build_claude_cli_deps`/`build_agent_deps` |
| `.../interactors/worker/subscription_runner.py` | pass the resolved token in `ctx_factory` |
| `projects/ui/src/modules/settings/SecretsPanel.tsx` | third secret field |
| `docs/dogfooding.md` | document the containerized-worker subscription path |
| tests (resolver, adapter env, allowlist, panel) | extend |

## Acceptance

With the worker image rebuilt and a `claude_oauth_token` saved in Settings → Secrets, a run started
against the **containerized** worker (`naaf_llm_provider=claude_cli`) executes `claude -p` inside the
container on the subscription — implement/verify/PR + lead-chat via the naaf MCP tools — with no
Anthropic key and no token in `.env`.
