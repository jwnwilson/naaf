# Secrets Management (Anthropic + GitHub keys) — Design

> Owner-scoped, **encrypted, write-only** secrets entered on a Settings page and **injected into
> agent runs**. The first, incremental step of the master design's `Secret` entity + management
> plane (spec §3/§5/§7) — real values stored encrypted + injected directly today; the
> credential-injecting egress proxy + placeholders are the deferred end-state.

## Problem

Agent credentials are global process env today: the Anthropic key is `naaf_anthropic_api_key`
baked into a single process-cached LLM adapter (`_deps()` `@lru_cache`), and `GH_TOKEN` is an
ambient env var the agent's shell (`LocalWorkspace.bash`, no `env=`) inherits. There is no UI to
manage them and no per-owner scoping — every run in a worker shares one set of keys, provided
out-of-band via env.

## Decisions (resolved during brainstorming)

- **Scope:** account-wide (**owner-scoped**) — one set per user, on a global Settings > Secrets page.
- **At rest:** **encrypted** (Fernet) with a master key from env; write-only API.
- **Env fallback:** a stored secret **overrides** the env value; when unset, fall back to the
  existing env `Settings` (so `make dev NAAF_AGENT_RUNTIME=claude_code` with env vars still works).
- **One PR** covering store + API + injection + UI.

## 1. Data model + encryption

New owner-scoped entity (mirrors `WorkItem`/`Run` persistence):

- Domain `Secret` (`domain/secrets/secret.py`): `owner_id: str`, `name: str`,
  `value_encrypted: str`, `hint: str` (last 4 plaintext chars, for display). Extends `Entity`
  (`id`/`created_at`/`updated_at`). The domain treats `value_encrypted` as opaque — no crypto in
  domain.
- `SecretRow` (`adapters/database/orm.py`): `(_Timestamped, Base)`, columns `name` (`String(64)`),
  `value_encrypted` (`Text`), `hint` (`String(8)`), with a **unique constraint on
  `(owner_id, name)`** (upsert target).
- `SecretRepository(SqlRepository[Secret])` + a `secrets` property on the UoW; imported in
  `subscription_runner` for the worker.
- Migration `0011_secrets` (`down_revision = "0010_run_pr_url"`).

**Allowlist of names** (`domain/secrets/secret.py`): `SECRET_NAMES = ("anthropic_api_key",
"github_token")`. The API rejects any other name.

**Cipher** (`adapters/security/cipher.py`): `SecretCipher` wrapping `cryptography.fernet.Fernet`,
built from `naaf_secret_key` (a base64 Fernet key). `encrypt(plaintext) -> str` /
`decrypt(token) -> str`. A new setting `naaf_secret_key: str = ""`. If empty, **writes fail
closed** (`SecretsNotConfigured` → HTTP 500 with a clear message) so plaintext is never stored;
reads/injection of an unset key simply fall back to env. `cryptography` added to server deps.

## 2. API — owner-scoped, write-only (`interactors/api/routes/secrets.py`)

- `GET /secrets` → `[{name, isSet, hint}]` for the known names (a row is `isSet` when present).
  **Never returns the value.**
- `PUT /secrets/{name}` `{value}` → validate `name ∈ SECRET_NAMES` (else 422); encrypt via
  `SecretCipher`; compute `hint = value[-4:]`; **upsert** the `(owner_id, name)` row; return
  `{name, isSet: true, hint}`.
- `DELETE /secrets/{name}` → delete the row if present; return `{name, isSet: false, hint: ""}`.
- Empty/blank value → 422. Registered in `register_routers`.

Contract: `SecretOut {name, isSet, hint}`, `SecretSetIn {value}`. Added to the OpenAPI yaml +
regenerated UI types.

## 3. Injection into runs (the core)

Resolved **per-owner** in `subscription_runner.ctx_factory` (it already derives `owner_id` and has
`uow.session`):

- `SecretResolver` (`adapters/agent/secrets_resolver.py`): given a `SecretRepository` (owner-scoped)
  + `SecretCipher` + the env `Settings`, returns resolved plaintext values with fallback:
  `anthropic_api_key = stored or settings.anthropic_api_key`,
  `github_token = stored or os.environ.get("GH_TOKEN", "")`.
- **Anthropic:** if the owner has a **stored** anthropic key, build a per-owner LLM adapter +
  `runtime`/`chat_responder`/`orchestrator` via a new `factory.build_agent_deps(settings, *,
  anthropic_api_key)` (a thin variant of the existing builders that overrides the key); otherwise
  reuse today's cached globals passed into `run_subscription`. Threaded into `HandlerContext`
  (`runtime`/`chat_responder`/`lead_orchestrator` already fields).
- **GitHub:** the resolved `github_token` is placed on `HandlerContext` (new field
  `github_token: str = ""`) and forwarded through `build_stage_context` into a `LocalWorkspace`
  built with a new `env` param; `LocalWorkspace.bash` runs `subprocess` with
  `env={**os.environ, **self._env}` so `GH_TOKEN` is set for the agent's `git`/`gh`. When unset,
  behavior is unchanged (ambient env inherited).

Per-owner adapter construction is cheap (wraps an HTTP client); building it per handled item is
acceptable. A per-owner cache is a deferred optimization.

## 4. UI — Settings > Secrets

- `SettingsSubnav` gains a **Secrets** entry; a new `SecretsPanel` (`modules/settings/`) renders two
  rows — **Anthropic API key** and **GitHub token** — each showing **Set ••••1234** (from `hint`)
  or **Not set**, a masked `TextInput` (`type=password`), a **Save** (PUT) and **Clear** (DELETE).
- Hooks: `useSecrets` (GET), `useSetSecret(name)` (PUT → invalidate `useSecrets`),
  `useDeleteSecret(name)`. The value is **never rendered**; the input clears on successful save.
- MSW mock handlers + a mock store (`db.secrets`) so the page is demoable offline; `PUT/GET/DELETE
  /secrets` added to `liveHandlers` (live-backed).

## Data flow

```
Settings > Secrets → PUT /secrets/anthropic_api_key {value}
  → validate name → SecretCipher.encrypt → upsert (owner-scoped) → {isSet, hint}
Run starts (worker) → ctx_factory(owner_id):
  SecretResolver(SecretRepository, SecretCipher, settings) → {anthropic_api_key, github_token}
   ├─ stored anthropic key? → build per-owner adapter/runtime/responder/orchestrator (else globals)
   └─ github_token → HandlerContext → LocalWorkspace(env={"GH_TOKEN": token})
  → agent uses the owner's model + gh credentials
```

## Error handling

- `naaf_secret_key` unset → PUT returns a clear 500 ("secret encryption key not configured"); the
  value is not stored. Reads/injection tolerate it (fall back to env).
- Real-mode run with neither a stored nor an env Anthropic key → the existing fail-fast in
  `build_llm_adapter` ("naaf_anthropic_api_key is required") still applies.
- API never logs or returns secret values; only `hint` (last 4) is exposed.

## Testing

- **Cipher:** encrypt→decrypt round-trips; distinct ciphertexts; fail-closed when key missing.
- **Repository:** owner-scoped round-trip + upsert on `(owner_id, name)`; owner isolation.
- **API:** PUT sets (returns `isSet`+`hint`, not value); GET never includes the value; DELETE
  clears; unknown/blank → 422; a second owner can't read the first's secrets.
- **Injection:** `SecretResolver` prefers stored over env and falls back when unset;
  `build_agent_deps` builds an adapter with the stored key; `LocalWorkspace.bash` includes
  `GH_TOKEN` in the subprocess env when provided.
- **UI:** `SecretsPanel` shows Set/Not-set from `hint`, saves via PUT (input clears), clears via
  DELETE; the value is never in the DOM after save.
- Keep `make coverage` (80%) + `make lint` green.

## Non-goals (deferred to the spec's end-state)

- No credential-injecting **egress proxy** / `__placeholder__` substitution / response redaction.
- No **GitHub App** per-run installation tokens (still a PAT).
- No per-project secrets, **no audit log**, no capability tiering, no rotation/expiry UI.
- No secret-value read-back API (write-only by design).

## Files (summary)

| File | Change |
|------|--------|
| `domain/secrets/secret.py` | **new** `Secret` entity + `SECRET_NAMES` |
| `adapters/security/cipher.py` | **new** `SecretCipher` (Fernet) + `SecretsNotConfigured` |
| `adapters/database/orm.py` | **new** `SecretRow` (unique owner_id+name) |
| `adapters/database/repositories.py` + `uow.py` | **new** `SecretRepository` + UoW property |
| `adapters/database/migrations/versions/0011_secrets.py` | **new** migration |
| `interactors/api/settings.py` | add `secret_key` |
| `interactors/api/routes/secrets.py` (+ `routes/__init__.py`, `contract.py`) | **new** write-only API |
| `adapters/agent/secrets_resolver.py` | **new** `SecretResolver` |
| `adapters/agent/factory.py` | `build_agent_deps(settings, *, anthropic_api_key)` |
| `adapters/agent/workspace/local.py` | `LocalWorkspace(env=…)`; `bash` merges env |
| `interactors/worker/handlers.py` | `HandlerContext.github_token`; pass env into workspace |
| `interactors/worker/subscription_runner.py` | resolve secrets per owner; per-owner deps |
| `projects/ui/openapi/naaf-api.yaml` (+ regen) | `SecretOut`/`SecretSetIn` |
| `projects/ui/src/modules/settings/SecretsPanel.tsx` + `SettingsSubnav` | **new** Secrets tab |
| `projects/ui/src/lib/api/hooks/useSecrets.ts` (+ set/delete) | **new** hooks |
| `projects/ui/src/lib/api/mocks/*` | mock secrets store + handlers |
| tests (cipher, repo, API, resolver, workspace env, UI) | **new** |

## Acceptance

From the Settings > Secrets page a user saves their Anthropic key + GitHub token (shown masked as
`••••1234`, never echoed). A run then uses the **owner's** stored key for the model and the owner's
token for `gh`/`git`, with env vars as the fallback when a secret isn't set — no keys in env files
or the transcript.
