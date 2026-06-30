# A2-4 — Wire the UI to the live A1 API — Design

**Date:** 2026-06-30
**Status:** Approved design, pending implementation plan
**Milestone:** A2-4 (the live-API swap deferred from A2)
**Builds on:** A1 control plane (`projects/server`) + A2 UI (`projects/ui`) — both merged to `main`.

## 1. Problem & goal

The A2 UI was built against an OpenAPI 3.1 contract and runs entirely on MSW-mocked data. The A1 backend exists for **Projects, WorkItems, and Teams/AgentDefinitions** — but its API shapes diverge systematically from the UI contract, so "flip MSW off and point at `/api`" does not work. A2-4 makes the backend **emit and accept the UI contract shapes exactly** for those three resource groups, then turns MSW off for them so the UI runs **hybrid**: live HTTP for Projects/WorkItems/Teams, mocked for everything else (runs, agents, inbox, chat, dashboard, budget, activity — no backend until A3/A5/A6).

### Success criterion

> With the backend running (`make run` on `:8000`) and the UI on `VITE_LIVE_API=true pnpm dev`, the **Board/List, Work-item Detail (spec/header), Settings, and the sidebar project list** render from the **real A1 database** (create a project + work items, change status, see them persist), while runs/inbox/dashboard/chat stay mocked. The default (`VITE_LIVE_API` unset) still serves the fully-mocked static demo unchanged. `make coverage` (80%) + `make lint` and `pnpm test`/`lint`/`build` stay green.

## 2. Decisions log

| Decision | Choice | Rationale |
|---|---|---|
| Where the shape translation lives | **Backend API interactor layer** (domain stays pure) | The API boundary is where external-contract adaptation belongs; the UI's generated types stay the contract, no UI mapping layer |
| Status enum | **Make the UI 5-set canonical in the backend domain** (`backlog/todo/in_progress/in_review/done`) | One status set end-to-end; avoids a lossy 7↔5 map; the backend's `approved/blocked/failed` aren't surfaced anywhere yet |
| MSW after the swap | **Hybrid via a `VITE_LIVE_API` flag** — live for 4 paths, mocked for the rest; default stays fully-mocked | Preserves the deployable static demo while enabling the live dev mode |
| Agent-run fields with no backend source | **Emit `null`/`[]` at the API layer** (not stored) | `assignedAgent`, `tokenUsage*`, `attachments` get real values in A3/A5; the UI already guards them optional |

## 3. Scope

**In scope:** align the A1 API for the 3 backed resource groups to the UI contract; the domain status 5-set change (+ transitions/tests/migration); additive `priority` (WorkItem) and `enabled`/`tokenLimit` (AgentDefinition) fields; list query-param mapping; the UI hybrid-MSW flag + handler split; a dev seed with demo data; backend + UI tests.

**Out of scope (stay mocked, no backend yet):** runs, live agents, inbox, chat/threads, dashboard metrics/token-usage/activity, budget — these are A3 (runs/agents), A5 (tokens/budget), A6 (chat/inbox). Also: real-time/SSE for live data; Auth0 (dev auth = single owner). The `/projects/{id}/board` **tree** endpoint is left as-is (the UI board view uses the flat `/work-items?project=` list).

## 4. Architecture — adaptation in `interactors/api/` (domain pure)

The translation is entirely in the API interactor layer except two genuine domain changes (status set, additive fields):

- **Contract-shaped API schemas** (camelCase, response + request) live in `interactors/api/` (e.g. `schemas_contract.py` or per-entity), plus **mappers** `domain ↔ schema`. The API emits exactly the UI shapes and accepts them on writes.
- **`CrudRouter` extended** with optional `to_response(domain) -> schema` and `from_create(schema) -> domain` / `from_update` mapper hooks, so the generic CRUD routes speak the contract while the repository still stores domain models. The hand-written nested-create / transition / board routes map the same way.
- **List query convention:** the work-items list accepts the contract's flat params (`?project=`, `?status=`, `?epic=`) and maps them to the repository filter DSL (`project_id`, `status`, `epic_id`). (The UI client sends each param flat, e.g. `?project=<id>`.)
- **Owner scoping** is unchanged (dev auth → `dev-user`; the UoW required-filter still applies); `owner_id` is never surfaced in the contract.

## 5. Field mapping (domain → contract; reverse on writes)

| Contract field | ← domain | Transform |
|---|---|---|
| **WorkItem** `id` | `id` | — |
| `projectId`, `parentId`, `createdAt`, `updatedAt` | `project_id`, `parent_id`, `created_at`, `updated_at` | camelCase |
| `type` | `kind` | rename |
| `spec` | `body` | rename |
| `status` | `status` | same 5 values — no transform |
| `priority` | `priority` *(new domain field, enum, default `medium`)* | — |
| `title` | `title` | — |
| `epicId`, `featureId` | walked from `parent_id` chain | computed (epic=root ancestor, feature=parent of a task) |
| `assignedAgent`, `tokenUsageThisRun`, `tokenUsageAllRuns`, `tokenLimit`, `attachments` | — | emit `null`/`[]` |
| **Project** `id`, `name` | `id`, `name` | — |
| `repoUrl`, `createdAt`, `updatedAt` | `repo_url`, `created_at`, `updated_at` | camelCase |
| `itemCount` | count of the project's work_items | computed |
| **Team** `id`, `name` (+ `createdAt`/`updatedAt` if the contract lists them) | `id`, `name` | — |
| **AgentDefinition** `id`, `teamId`, `role` | `id`, `team_id`, `role` | camelCase |
| `model` | `model_alias` | rename |
| `systemPrompt` | `persona_prompt` | rename |
| `enabled`, `tokenLimit` | new domain fields (`enabled: bool = True`, `token_limit: int = 200000`) | — |

Backend-only fields not in the contract (`autonomy_level`, `repo_path`, `team_id` on Project, `runtime_adapter`, `memory_scope`, `capability_grants`) are **not surfaced**. Create/update request schemas accept the contract's camelCase fields and map to domain (`type→kind`, `spec→body`, `parentId→parent_id`, `model→model_alias`, `systemPrompt→persona_prompt`).

## 6. Domain changes

1. **Status 5-set:** `WorkItemStatus` → `BACKLOG="backlog"`, `TODO="todo"`, `IN_PROGRESS="in_progress"`, `IN_REVIEW="in_review"`, `DONE="done"`. Rewire `domain/transitions.py` (the legal-edge table) to the 5 states; update the A1 transition + work-item + API tests that referenced `to_do/approved/blocked/failed`. The transition route's `validate_transition` now uses the 5-set.
2. **Additive fields:** `WorkItem.priority` (`Priority` enum `low/medium/high/urgent`, default `medium`); `AgentDefinition.enabled: bool = True`, `token_limit: int = 200000`. Add to domain models, ORM rows, and the Alembic baseline-or-new migration.
3. **Migration:** an Alembic migration that (a) adds the new columns and (b) **remaps existing status values** (`to_do→todo`, `approved→done`, `blocked→todo`, `failed→todo`). SQLite-in-memory tests use `create_all`; Postgres is migrated.

## 7. UI side — hybrid MSW via `VITE_LIVE_API`

Because the backend now emits the contract, the UI needs **no data mapping** — the generated types already match. Only MSW changes:

- Split `src/lib/api/mocks/handlers.ts` into **`mockOnlyHandlers`** (runs, agents, runs-stream, inbox, threads, dashboard metrics/token-usage, activity, budget) and **`liveHandlers`** (projects, work-items, projects/:id/work-items, work-items/:id + transition, teams, agent-definitions).
- `browser.ts`/`server.ts` register **all** handlers when `import.meta.env.VITE_LIVE_API !== "true"` (default — fully-mocked static demo, unchanged); register **only `mockOnlyHandlers`** when `VITE_LIVE_API === "true"`, so the live paths fall through to the real `/api` (Vite already proxies `/api`→`:8000`).
- No change to the client, hooks, or screens. Vitest runs with the flag unset (fully mocked) → existing UI tests are unaffected.

## 8. Dev workflow & seed

- **Backend:** `docker compose up -d postgres` → `make db-upgrade` → seed → `make run` (uvicorn `:8000`).
- **UI:** `VITE_LIVE_API=true pnpm dev` (`:5173`, proxy `/api`→`:8000`) → Projects/WorkItems/Teams live, the rest mocked.
- **Seed:** extend `interactors/cli/seed.py` (or add a `cli/seed_demo.py`) to create a **demo project + ~6 work items across the 5 statuses with varied priorities** (plus the existing default team) so the live board/list render non-empty. Idempotent, owner `dev-user`.

## 9. Testing

- **Backend (pytest, 80% gate):** update the A1 status/transition/work-item/API tests to the 5-set. New unit tests for the mappers (`domain ↔ contract`: camelCase keys, `type`/`spec`/`model`/`systemPrompt`, computed `itemCount` and `epicId`/`featureId`, `null` agent fields). New API integration tests asserting the **contract shape** is emitted (camelCase JSON keys present; backend-only fields absent), the `?project=`/`?status=` list filter works, nested-create maps `type`/`spec`/`parentId`, and transition accepts the new statuses. A migration test for the status remap.
- **UI (vitest):** existing suite runs fully-mocked (flag unset) and must stay green. Add a test that under `VITE_LIVE_API`, the handler set excludes the live paths (so they bypass to `/api`).
- **Manual E2E:** with backend + `VITE_LIVE_API=true`, create a project, add work items, change status on the board, confirm persistence across refresh.
- **Contract-drift guard (follow-up, noted not built):** diff FastAPI's generated OpenAPI for the 4 groups against `projects/ui/openapi/naaf-api.yaml`.

## 10. Error handling & conventions (carried)

- Envelope `{success, data, error}` (+ `meta`) is already shared by both sides — unchanged. Domain errors map to HTTP via the existing handlers; the UI client unwraps the envelope and throws `ApiError`.
- Immutability (`model_copy`), owner-scoping, UUID-hex ids, TDD, `<type>: <description>` commits — all unchanged.

## 11. Implementation phasing (for the plan)

One milestone, phased so each phase is independently reviewable: (1) domain status 5-set + transitions + A1 test updates + migration; (2) additive `priority`/`enabled`/`tokenLimit` fields + migration; (3) contract API schemas + mappers + `CrudRouter` mapper hooks + list-param mapping; (4) backend API integration tests asserting contract shape + the dev seed; (5) UI hybrid-MSW flag + handler split + its test; (6) manual end-to-end verification + docs note.
