# A2 Data Layer — OpenAPI contract + client + React Query + MSW — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the swappable data seam: an OpenAPI 3.1 contract (the single source of truth), generated TS types, an envelope-aware typed client, React Query wiring, and an MSW mock implementation (handlers + fixtures + SSE) so screens can fetch real HTTP that is intercepted by mocks today and points at a real backend later.

**Architecture:** `openapi/naaf-api.yaml` → `openapi-typescript` generates `src/lib/api/schema.d.ts`. `client.ts` wraps `fetch`, unwraps the `{success,data,error}` envelope (throws `ApiError`), base `/api`. React Query owns server-state via per-resource hooks and a key factory. MSW (`browser` + `node`) intercepts every contract path against in-memory fixtures; SSE endpoints stream via a small mock streamer consumed by a `useEventSource` hook.

**Tech Stack:** @tanstack/react-query, msw, openapi-typescript (dev), plus the Task-1 Vite/vitest stack.

## Global Constraints

- Package manager **pnpm** (never npm); all commands from `projects/ui/`. This plan builds ONLY the data layer — no screens, no app shell.
- **The contract is the source of truth.** Endpoint groups + entity shapes come from the spec `docs/superpowers/specs/2026-06-29-a2-ui-design.md` §4 and the handoff data model in `docs/design/README.md` § "Data Model (from naaf)". The work-item status set is the **UI-canonical** one: `backlog · todo · in_progress · in_review · done` (the spec's §4 reconciliation note).
- Every response is the envelope `{success: boolean, data: T | null, error: string | null}`; list responses add `meta: {total: number, page_size: number, page_number: number}`.
- Types are **generated** from the OpenAPI doc (`pnpm gen:api`); never hand-write `schema.d.ts`. Hooks type their payloads from `components["schemas"][...]`.
- TypeScript strict; no `any` in exported signatures. Commit format `<type>: <description>`; one focused commit per task. TDD. Keep `pnpm test`/`pnpm lint`/`pnpm build` green each task.
- Work in the `feat/a2-ui` worktree at `.worktrees/a2-ui`; the design-system foundation (Plan 1) is already merged into this branch.

---

## File Structure

```
projects/ui/
  openapi/naaf-api.yaml              # OpenAPI 3.1 contract (hand-authored)
  package.json                       # + @tanstack/react-query, msw, openapi-typescript; + gen:api script
  src/lib/api/
    schema.d.ts                      # GENERATED (pnpm gen:api) — committed
    client.ts                        # apiFetch<T> (+ apiPost/apiPatch/apiDelete) + ApiError + envelope unwrap
    queryKeys.ts                     # key factories per resource
    queryClient.tsx                  # QueryClientProvider wrapper + createQueryClient
    hooks/
      index.ts
      useProjects.ts useBoard.ts useWorkItem.ts useInbox.ts useThreads.ts
      useDashboard.ts useAgents.ts useBudget.ts useSettings.ts useAgentDefinitions.ts
      useRun.ts                      # SSE
    mocks/
      browser.ts server.ts           # MSW setupWorker / setupServer
      handlers.ts                    # implement every contract path
      sse.ts                         # mock run-log + chat streamers
      db.ts                          # in-memory fixture store (seed + helpers)
      fixtures/                      # seed data modules per resource
  src/lib/hooks/useEventSource.ts    # generic SSE subscription hook
  src/test/setup.ts                  # + MSW node server lifecycle (beforeAll/afterEach/afterAll)
```

---

### Task 1: Dependencies + OpenAPI contract + type generation

**Files:**
- Modify: `projects/ui/package.json` (deps + `gen:api` script)
- Create: `projects/ui/openapi/naaf-api.yaml`, `projects/ui/src/lib/api/schema.d.ts` (generated), `projects/ui/openapi/contract.test.ts`

**Interfaces:**
- Produces: a valid OpenAPI 3.1 doc covering every resource group; `pnpm gen:api` regenerates `schema.d.ts`; the generated `paths` + `components["schemas"]` are importable and compile.

- [ ] **Step 1: Add deps + script**

In `projects/ui/package.json` add to `dependencies`: `"@tanstack/react-query": "^5.59.0"`, `"msw": "^2.6.0"`. To `devDependencies`: `"openapi-typescript": "^7.4.0"`, `"yaml": "^2.5.0"`. Add scripts: `"gen:api": "openapi-typescript openapi/naaf-api.yaml -o src/lib/api/schema.d.ts"`. Then `cd projects/ui && pnpm install`.

- [ ] **Step 2: Write the failing contract test**

`projects/ui/openapi/contract.test.ts`:
```ts
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { parse } from "yaml";
import { describe, expect, it } from "vitest";

const doc = parse(readFileSync(resolve(__dirname, "naaf-api.yaml"), "utf8"));

describe("OpenAPI contract", () => {
  it("is OpenAPI 3.1 with an envelope-based schema set", () => {
    expect(doc.openapi).toMatch(/^3\.1/);
    expect(doc.components.schemas).toHaveProperty("Envelope");
    expect(doc.components.schemas).toHaveProperty("WorkItem");
    expect(doc.components.schemas).toHaveProperty("Project");
    expect(doc.components.schemas).toHaveProperty("AgentRun");
    expect(doc.components.schemas).toHaveProperty("InboxItem");
  });

  it("defines the core paths every screen needs", () => {
    for (const path of [
      "/projects", "/projects/{id}", "/projects/{id}/board", "/work-items",
      "/work-items/{id}", "/work-items/{id}/transition", "/projects/{id}/work-items",
      "/agents", "/runs/{id}", "/runs/{id}/stream", "/inbox", "/threads",
      "/dashboard/metrics", "/dashboard/token-usage", "/budget",
      "/agent-definitions",
    ]) {
      expect(doc.paths, `missing path ${path}`).toHaveProperty([path]);
    }
  });

  it("uses the UI-canonical work-item status enum", () => {
    expect(doc.components.schemas.WorkItem.properties.status.enum).toEqual(
      ["backlog", "todo", "in_progress", "in_review", "done"],
    );
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd projects/ui && pnpm test openapi/contract`
Expected: FAIL — `naaf-api.yaml` missing.

- [ ] **Step 4: Author the OpenAPI doc**

Create `projects/ui/openapi/naaf-api.yaml` as OpenAPI **3.1.0**. Author it to satisfy the test and cover the spec's §4 contract table. Requirements:

- `components.schemas` includes a generic envelope plus every entity from `docs/design/README.md` § Data Model, with field names/types matching that model (and the UI-canonical status enum):
  - `Envelope` (`{ success: boolean, data: {}|null nullable, error: string|null nullable, meta: Meta|null }`), `Meta` (`{ total, page_size, page_number }` integers).
  - `Project` (`id, name, repoUrl, itemCount, createdAt, updatedAt`), `WorkItem` (`id, type[epic|feature|task], title, status[backlog|todo|in_progress|in_review|done], priority[low|medium|high|urgent], assignedAgent?(Agent), epicId?, featureId?, projectId, tokenUsageThisRun?, tokenUsageAllRuns?, tokenLimit?, spec?(markdown), attachments?(Attachment[]), createdAt, updatedAt`), `Attachment` (`id, name, size, kind`), `Agent` (`id, type[lead|sub], model, status[running|idle|paused], currentItemId?, progress?, tokenUsage?, tokenLimit`), `Team` (`id, name`), `AgentDefinition` (`id, teamId, role, model, tokenLimit, systemPrompt, enabled`), `InboxItem` (`id, type[action_needed|review_needed|info|resolved], title, preview, agentId, workItemId, conversationId, createdAt, read`), `Message` (`id, conversationId, role[user|agent|lead_agent], agentId?, content, createdAt`), `AgentRun` (`id, agentId, workItemId, status[running|paused|complete|failed], steps(RunStep[]), logLines(LogLine[]), tokenUsage, cost, startedAt`), `RunStep` (`index, label[Plan|Read|Analyze|Generate|Test|PR], status[done|active|pending]`), `LogLine` (`timestamp, type[tool_call|result|status], tool?, target?, message?`), `DashboardMetrics`, `TokenUsagePoint` (`day, tokens`), `ActivityEvent`, `Budget` (`used, limit`).
- `paths` covers the spec §4 table. Each non-SSE response body is an `Envelope` whose `data` is the relevant schema (or an array for lists, with `meta` populated). For each list endpoint include `filters`/`page_size`/`page_number`/`order_by` query params where the spec lists them. SSE endpoints (`/runs/{id}/stream`, and a chat stream under `/threads/{id}/stream` if present) respond `text/event-stream`.
- Write at least two paths **fully** as the pattern (e.g. `GET /projects` list + `GET /work-items/{id}`), then complete the rest following that pattern. The contract test pins the path set + the status enum; ensure all assert-listed paths exist.

Example pattern (include this shape, expand to all paths):
```yaml
openapi: 3.1.0
info: { title: NAAF API, version: 0.1.0 }
paths:
  /projects:
    get:
      operationId: listProjects
      parameters:
        - { name: page_size, in: query, schema: { type: integer, default: 50 } }
        - { name: page_number, in: query, schema: { type: integer, default: 1 } }
        - { name: order_by, in: query, schema: { type: string, default: "-createdAt" } }
      responses:
        "200":
          description: ok
          content:
            application/json:
              schema:
                allOf:
                  - $ref: "#/components/schemas/Envelope"
                  - type: object
                    properties:
                      data: { type: array, items: { $ref: "#/components/schemas/Project" } }
components:
  schemas:
    Meta:
      type: object
      properties:
        total: { type: integer }
        page_size: { type: integer }
        page_number: { type: integer }
    Envelope:
      type: object
      required: [success]
      properties:
        success: { type: boolean }
        data: { nullable: true }
        error: { type: string, nullable: true }
        meta: { $ref: "#/components/schemas/Meta", nullable: true }
    WorkItem:
      type: object
      properties:
        id: { type: string }
        type: { type: string, enum: [epic, feature, task] }
        title: { type: string }
        status: { type: string, enum: [backlog, todo, in_progress, in_review, done] }
        # …remaining fields per the handoff data model…
    # …all other schemas…
```

- [ ] **Step 5: Generate types + run tests**

Run: `cd projects/ui && pnpm gen:api && pnpm test openapi/contract && pnpm lint`
Expected: `schema.d.ts` written; contract tests PASS; `tsc --noEmit` clean (the generated file compiles).

- [ ] **Step 6: Commit**

```bash
git add projects/ui/openapi projects/ui/src/lib/api/schema.d.ts projects/ui/package.json projects/ui/pnpm-lock.yaml
git commit -m "feat(ui): OpenAPI 3.1 contract + generated types"
```

---

### Task 2: Envelope-aware client

**Files:**
- Create: `projects/ui/src/lib/api/client.ts`, `projects/ui/src/lib/api/client.test.ts`

**Interfaces:**
- Consumes: `schema.d.ts` (for typing at call sites; the client itself is generic).
- Produces:
  - `class ApiError extends Error { status: number }`.
  - `apiFetch<T>(path: string, init?: RequestInit): Promise<T>` — fetches `${BASE}${path}`, parses JSON, returns `body.data` on `success:true`, throws `ApiError(body.error, status)` on `success:false` or non-2xx or network error.
  - `apiList<T>(path, params?): Promise<{ results: T[]; meta: Meta }>` — GET with query params (`filters` JSON-stringified if object), returns `{ results: data, meta }`.
  - `apiPost/apiPatch/apiDelete` thin helpers. `BASE = "/api"`.

- [ ] **Step 1: Write the failing tests**

`projects/ui/src/lib/api/client.test.ts`:
```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch, apiList } from "./client";

function mockFetch(body: unknown, ok = true, status = 200) {
  return vi.fn().mockResolvedValue({
    ok, status, json: () => Promise.resolve(body),
  } as unknown as Response);
}

afterEach(() => vi.restoreAllMocks());

describe("apiFetch", () => {
  it("unwraps the envelope data on success", async () => {
    vi.stubGlobal("fetch", mockFetch({ success: true, data: { id: "p1" }, error: null }));
    await expect(apiFetch("/projects/p1")).resolves.toEqual({ id: "p1" });
  });

  it("throws ApiError with the message on success:false", async () => {
    vi.stubGlobal("fetch", mockFetch({ success: false, data: null, error: "not found" }, false, 404));
    await expect(apiFetch("/projects/x")).rejects.toMatchObject({ message: "not found", status: 404 });
    await expect(apiFetch("/projects/x")).rejects.toBeInstanceOf(ApiError);
  });

  it("apiList returns results + meta", async () => {
    vi.stubGlobal("fetch", mockFetch({ success: true, data: [{ id: "a" }], error: null, meta: { total: 1, page_size: 50, page_number: 1 } }));
    const page = await apiList("/projects");
    expect(page.results).toHaveLength(1);
    expect(page.meta.total).toBe(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm test src/lib/api/client`
Expected: FAIL — `./client` not found.

- [ ] **Step 3: Implement the client**

`projects/ui/src/lib/api/client.ts`:
```ts
export const BASE = "/api";

export type Meta = { total: number; page_size: number; page_number: number };
type Envelope<T> = { success: boolean; data: T; error: string | null; meta?: Meta };

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<Envelope<T>> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
      ...init,
    });
  } catch (e) {
    throw new ApiError((e as Error).message || "network error", 0);
  }
  const body = (await res.json()) as Envelope<T>;
  if (!res.ok || !body.success) {
    throw new ApiError(body.error ?? `request failed (${res.status})`, res.status);
  }
  return body;
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  return (await request<T>(path, init)).data;
}

export async function apiList<T>(
  path: string,
  params?: Record<string, unknown>,
): Promise<{ results: T[]; meta: Meta }> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v === undefined || v === null) continue;
    qs.set(k, typeof v === "object" ? JSON.stringify(v) : String(v));
  }
  const suffix = qs.toString() ? `?${qs}` : "";
  const body = await request<T[]>(`${path}${suffix}`);
  return { results: body.data, meta: body.meta ?? { total: body.data.length, page_size: 50, page_number: 1 } };
}

export const apiPost = <T>(path: string, json: unknown) =>
  apiFetch<T>(path, { method: "POST", body: JSON.stringify(json) });
export const apiPatch = <T>(path: string, json: unknown) =>
  apiFetch<T>(path, { method: "PATCH", body: JSON.stringify(json) });
export const apiDelete = (path: string) => apiFetch<void>(path, { method: "DELETE" });
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/ui && pnpm test src/lib/api/client`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/lib/api/client.ts projects/ui/src/lib/api/client.test.ts
git commit -m "feat(ui): envelope-aware API client"
```

---

### Task 3: MSW mock implementation (handlers + fixtures + lifecycle)

**Files:**
- Create: `projects/ui/src/lib/api/mocks/db.ts`, `handlers.ts`, `server.ts`, `browser.ts`, `fixtures/index.ts` (+ per-resource fixture modules)
- Modify: `projects/ui/src/test/setup.ts` (start the MSW node server for tests)
- Test: `projects/ui/src/lib/api/mocks/handlers.test.ts`

**Interfaces:**
- Consumes: `apiFetch`/`apiList` (Task 2); the contract paths (Task 1).
- Produces: `db` (in-memory seeded store), `handlers` (an array of MSW request handlers implementing every contract path, returning enveloped fixtures), `server` (node `setupServer(...handlers)`), `worker` (browser `setupWorker(...handlers)`). Test setup installs `server` with `onUnhandledRequest: "error"`.

- [ ] **Step 1: Write the failing test**

`projects/ui/src/lib/api/mocks/handlers.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { apiFetch, apiList } from "../client";

// MSW node server is started globally in src/test/setup.ts
describe("mock handlers", () => {
  it("serves a paginated project list with meta", async () => {
    const page = await apiList("/projects");
    expect(page.results.length).toBeGreaterThan(0);
    expect(page.meta.total).toBeGreaterThanOrEqual(page.results.length);
    expect(page.results[0]).toHaveProperty("name");
  });

  it("serves a single work item with the UI status set", async () => {
    const board = await apiFetch<{ id: string }[]>("/projects/proj-1/board");
    expect(Array.isArray(board)).toBe(true);
  });

  it("serves dashboard metrics and budget", async () => {
    await expect(apiFetch("/dashboard/metrics")).resolves.toBeTruthy();
    await expect(apiFetch("/budget")).resolves.toHaveProperty("limit");
  });

  it("404s an unknown project as an ApiError", async () => {
    await expect(apiFetch("/projects/nope")).rejects.toMatchObject({ status: 404 });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm test src/lib/api/mocks/handlers`
Expected: FAIL — mocks not set up / unhandled request error.

- [ ] **Step 3: Implement fixtures, db, handlers, server, browser; wire test setup**

`fixtures/` — author realistic seed data spanning every visual state the screens need (from the spec §8 fixtures list): ≥2 projects; a board tree of epics→features→tasks across all five statuses incl. `backlog` and `done`, with priorities and some `assignedAgent`/token usage; agents running+idle+paused; one `AgentRun` with completed/active/pending steps + several `LogLine`s; inbox items of all four `type`s incl. `resolved`; threads with user+agent messages; dashboard metrics + a ~7-day `TokenUsagePoint` series + activity events; a `Budget` near a threshold; lead + subagent `AgentDefinition`s. Export a single `seed` object from `fixtures/index.ts`.

`db.ts` — load `seed` into mutable in-memory arrays/maps with lookup + filter helpers (e.g. `db.projects`, `db.workItems`, `db.boardFor(projectId)`, `db.findProject(id)`).

`handlers.ts` — one MSW `http.<method>` handler per contract path, each returning the envelope. Helper:
```ts
import { HttpResponse, http } from "msw";
const ok = (data: unknown, meta?: unknown) => HttpResponse.json({ success: true, data, error: null, meta: meta ?? null });
const notFound = () => HttpResponse.json({ success: false, data: null, error: "not found" }, { status: 404 });
// example:
http.get("/api/projects", () => ok(db.projects, { total: db.projects.length, page_size: 50, page_number: 1 })),
http.get("/api/projects/:id", ({ params }) => { const p = db.findProject(params.id as string); return p ? ok(p) : notFound(); }),
```
Implement handlers for every path the contract (and `handlers.test.ts`) exercises, including `/projects/:id/board`, `/work-items`, `/work-items/:id`, `/agents`, `/runs/:id`, `/inbox`, `/threads`, `/dashboard/metrics`, `/dashboard/token-usage`, `/budget`, `/agent-definitions`. (SSE handlers are added in Task 5.)

`server.ts`: `export const server = setupServer(...handlers);`
`browser.ts`: `export const worker = setupWorker(...handlers);`

`src/test/setup.ts` — append:
```ts
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "../lib/api/mocks/server";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/ui && pnpm test src/lib/api/mocks/handlers && pnpm lint`
Expected: PASS; lint clean.

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/lib/api/mocks projects/ui/src/test/setup.ts
git commit -m "feat(ui): MSW mock handlers + fixtures"
```

---

### Task 4: React Query wiring + resource hooks

**Files:**
- Create: `projects/ui/src/lib/api/queryClient.tsx`, `queryKeys.ts`, `hooks/index.ts`, and the resource hooks (`useProjects.ts`, `useBoard.ts`, `useWorkItem.ts`, `useInbox.ts`, `useThreads.ts`, `useDashboard.ts`, `useAgents.ts`, `useBudget.ts`, `useSettings.ts`/`useAgentDefinitions.ts`)
- Test: `projects/ui/src/lib/api/hooks/hooks.test.tsx`

**Interfaces:**
- Consumes: `apiFetch`/`apiList` (Task 2); MSW handlers (Task 3); generated `schema.d.ts` types.
- Produces:
  - `createQueryClient()` + `<QueryProvider>` wrapper.
  - `queryKeys` factory (`queryKeys.projects()`, `queryKeys.board(projectId)`, `queryKeys.workItem(id)`, `queryKeys.inbox(filter?)`, `queryKeys.dashboard()`, `queryKeys.agents()`, `queryKeys.budget()`, `queryKeys.agentDefinitions()`, `queryKeys.threads()`).
  - One hook per resource returning React Query results typed from `components["schemas"]`. List hooks return `{ data: { results, meta }, ... }`.

- [ ] **Step 1: Write the failing test**

`projects/ui/src/lib/api/hooks/hooks.test.tsx`:
```tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../queryClient";
import { useProjects } from "./useProjects";
import { useBudget } from "./useBudget";

function wrapper() {
  const client = createQueryClient();
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

describe("resource hooks", () => {
  it("useProjects loads the mock project list", async () => {
    const { result } = renderHook(() => useProjects(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data!.results.length).toBeGreaterThan(0);
  });

  it("useBudget loads the budget", async () => {
    const { result } = renderHook(() => useBudget(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveProperty("limit");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm test src/lib/api/hooks`
Expected: FAIL — modules not found.

- [ ] **Step 3: Implement queryClient, keys, hooks**

`queryClient.tsx`:
```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false, staleTime: 30_000 } },
  });
}

export function QueryProvider({ children, client = createQueryClient() }: { children: ReactNode; client?: QueryClient }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
```

`queryKeys.ts`:
```ts
export const queryKeys = {
  projects: () => ["projects"] as const,
  board: (projectId: string) => ["board", projectId] as const,
  workItem: (id: string) => ["work-item", id] as const,
  inbox: (filter?: string) => ["inbox", filter ?? "all"] as const,
  threads: () => ["threads"] as const,
  dashboard: () => ["dashboard"] as const,
  agents: () => ["agents"] as const,
  budget: () => ["budget"] as const,
  agentDefinitions: () => ["agent-definitions"] as const,
  run: (id: string) => ["run", id] as const,
};
```

Hooks — type payloads from the generated schema. Pattern (`useProjects.ts`):
```ts
import { useQuery } from "@tanstack/react-query";
import { apiList, type Meta } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type Project = components["schemas"]["Project"];

export function useProjects() {
  return useQuery({
    queryKey: queryKeys.projects(),
    queryFn: () => apiList<Project>("/projects"),
  });
}
export type { Meta };
```
Implement the remaining hooks analogously: `useBoard(projectId)` → `apiFetch<WorkItem[]>('/projects/'+projectId+'/board')`; `useWorkItem(id)` → `apiFetch<WorkItem>('/work-items/'+id)`; `useInbox(filter?)` → `apiList<InboxItem>('/inbox', filter ? { type: filter } : undefined)`; `useThreads()`; `useDashboard()` → `apiFetch<DashboardMetrics>('/dashboard/metrics')` (+ a `useTokenUsage()` for the series); `useAgents()` → `apiList<Agent>('/agents')` (or `apiFetch<Agent[]>`); `useBudget()` → `apiFetch<Budget>('/budget')`; `useAgentDefinitions()` → `apiList<AgentDefinition>('/agent-definitions')`. `hooks/index.ts` re-exports all hooks + their entity types.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/ui && pnpm test src/lib/api/hooks && pnpm lint`
Expected: PASS; lint clean.

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/lib/api/queryClient.tsx projects/ui/src/lib/api/queryKeys.ts projects/ui/src/lib/api/hooks
git commit -m "feat(ui): react-query wiring + resource hooks"
```

---

### Task 5: SSE — mock streamer + useEventSource + useRun

**Files:**
- Create: `projects/ui/src/lib/hooks/useEventSource.ts`, `projects/ui/src/lib/api/hooks/useRun.ts`, `projects/ui/src/lib/api/mocks/sse.ts`
- Modify: `projects/ui/src/lib/api/mocks/handlers.ts` (add the `/runs/:id/stream` SSE handler)
- Test: `projects/ui/src/lib/api/hooks/useRun.test.tsx`

**Interfaces:**
- Consumes: MSW (Task 3), React Query (Task 4).
- Produces:
  - `useEventSource<T>(url: string | null, onMessage: (data: T) => void)` — opens an `EventSource`, parses each `event.data` as JSON, calls `onMessage`; closes on unmount / when `url` is null.
  - `useRun(runId: string)` — `useQuery` for the run snapshot (`/runs/:id`) plus a live subscription that appends streamed `LogLine`s / advances `RunStep`s into local state; returns `{ run, logLines, isStreaming }`.
  - `mocks/sse.ts` streams a scripted sequence of log lines + step transitions for the fixture run; the handler responds `text/event-stream`.

- [ ] **Step 1: Write the failing test**

`projects/ui/src/lib/api/hooks/useRun.test.tsx`:
```tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../queryClient";
import { useRun } from "./useRun";

function wrapper() {
  const client = createQueryClient();
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

describe("useRun", () => {
  it("loads the run snapshot from the mock", async () => {
    const { result } = renderHook(() => useRun("run-1"), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.run).toBeTruthy());
    expect(result.current.run!.steps.length).toBeGreaterThan(0);
  });
});
```
(Note: this test asserts the snapshot load — the cheapest reliable SSE assertion in jsdom. The live-stream append is exercised by the Agent-Monitor screen plan; jsdom's EventSource is limited, so keep the streaming assertion out of the unit test and verify the snapshot path here. Do NOT add a flaky timer-based stream assertion.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm test src/lib/api/hooks/useRun`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement useEventSource, sse mock, useRun, handler**

`useEventSource.ts`:
```ts
import { useEffect, useRef } from "react";

export function useEventSource<T>(url: string | null, onMessage: (data: T) => void) {
  const cb = useRef(onMessage);
  cb.current = onMessage;
  useEffect(() => {
    if (!url) return;
    const es = new EventSource(url);
    es.onmessage = (e) => {
      try { cb.current(JSON.parse(e.data) as T); } catch { /* ignore malformed frame */ }
    };
    return () => es.close();
  }, [url]);
}
```

`mocks/sse.ts` — export a function building a `ReadableStream`/`text/event-stream` body that emits a scripted sequence (a few `LogLine` frames then a `RunStep` transition), each as `data: ${JSON.stringify(frame)}\n\n`. Wire it in `handlers.ts`:
```ts
http.get("/api/runs/:id/stream", () => new HttpResponse(buildRunStream(), {
  headers: { "content-type": "text/event-stream" },
})),
```

`useRun.ts`:
```ts
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../client";
import { queryKeys } from "../queryKeys";
import { useEventSource } from "../../hooks/useEventSource";
import type { components } from "../schema";

export type AgentRun = components["schemas"]["AgentRun"];
export type LogLine = components["schemas"]["LogLine"];

export function useRun(runId: string) {
  const query = useQuery({ queryKey: queryKeys.run(runId), queryFn: () => apiFetch<AgentRun>(`/runs/${runId}`) });
  const [streamed, setStreamed] = useState<LogLine[]>([]);
  useEventSource<LogLine>(query.data ? `/api/runs/${runId}/stream` : null, (line) =>
    setStreamed((prev) => [...prev, line]),
  );
  const logLines = [...(query.data?.logLines ?? []), ...streamed];
  return { run: query.data, logLines, isStreaming: !!query.data && query.data.status === "running" };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/ui && pnpm test src/lib/api/hooks/useRun && pnpm lint`
Expected: PASS; lint clean.

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/lib/hooks/useEventSource.ts projects/ui/src/lib/api/hooks/useRun.ts projects/ui/src/lib/api/mocks/sse.ts projects/ui/src/lib/api/mocks/handlers.ts projects/ui/src/lib/api/hooks/useRun.test.tsx
git commit -m "feat(ui): SSE mock streamer + useRun hook"
```

---

### Task 6: Mock startup wiring + full data-layer gate

**Files:**
- Modify: `projects/ui/src/main.tsx` (start MSW worker when `VITE_USE_MOCKS`), `projects/ui/.env` (`VITE_USE_MOCKS=true`), `projects/ui/package.json` (msw `init` if needed)
- Create: `projects/ui/public/mockServiceWorker.js` (via `pnpm dlx msw init public`), `projects/ui/src/lib/api/index.ts` (barrel)
- Test: `projects/ui/src/lib/api/index.test.ts`

**Interfaces:**
- Produces: a browser that boots the MSW worker before rendering (so `pnpm dev`/`build` run fully mocked), and an `api` barrel re-exporting the client, hooks, query client, and query keys for screens to import.

- [ ] **Step 1: Write the failing barrel test**

`projects/ui/src/lib/api/index.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import * as api from "./index";

describe("api barrel", () => {
  it("re-exports the client, query wiring, and hooks", () => {
    for (const name of ["apiFetch", "apiList", "ApiError", "createQueryClient", "QueryProvider",
      "queryKeys", "useProjects", "useBoard", "useWorkItem", "useInbox", "useDashboard",
      "useAgents", "useBudget", "useAgentDefinitions", "useRun"]) {
      expect(api[name as keyof typeof api]).toBeDefined();
    }
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm test src/lib/api/index`
Expected: FAIL — barrel missing.

- [ ] **Step 3: Implement barrel + mock startup + worker asset**

Generate the worker asset: `cd projects/ui && pnpm dlx msw init public --save` (creates `public/mockServiceWorker.js`).

`src/lib/api/index.ts`:
```ts
export * from "./client";
export * from "./queryClient";
export * from "./queryKeys";
export * from "./hooks";
```
(Ensure `hooks/index.ts` re-exports every hook incl. `useRun`.)

`projects/ui/.env`:
```
VITE_USE_MOCKS=true
```

`src/main.tsx` — start the worker before render when mocks are enabled:
```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";

async function enableMocks() {
  if (import.meta.env.VITE_USE_MOCKS !== "true") return;
  const { worker } = await import("./lib/api/mocks/browser");
  await worker.start({ onUnhandledRequest: "bypass" });
}

enableMocks().then(() => {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <div className="min-h-screen bg-bg-base text-text-1">NAAF UI — data layer ready</div>
    </StrictMode>,
  );
});
```

- [ ] **Step 4: Run the full data-layer gate**

Run: `cd projects/ui && pnpm test && pnpm lint && pnpm build`
Expected: every data-layer test passes; eslint + tsc clean; vite build emits `dist/` (with the worker asset). Confirm `git status` is clean afterward (no stray emitted files).

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/main.tsx projects/ui/src/lib/api/index.ts projects/ui/src/lib/api/index.test.ts projects/ui/.env projects/ui/public/mockServiceWorker.js
git commit -m "feat(ui): boot MSW worker + api barrel"
```

---

## Self-Review

**1. Spec coverage (against spec §4 contract, §7 data layer, §8):** Task 1 = OpenAPI doc covering every §4 endpoint group + handoff entity schemas + the UI-canonical status enum (§4 reconciliation). Task 2 = envelope-aware client (§7). Task 3 = MSW handlers + fixtures spanning every visual state (§8 fixtures list). Task 4 = React Query + per-resource hooks (§7 hooks list: useProjects/useBoard/useWorkItem/useInbox/useThreads/useDashboard/useAgents/useBudget/useSettings→useAgentDefinitions). Task 5 = SSE useRun + useEventSource (§7 SSE). Task 6 = mock startup (VITE_USE_MOCKS, §8/§10) + barrel. The live-API swap and screens are out of scope (later plans), as the spec states.

**2. Placeholder scan:** No "TBD"/"implement later". The two large declarative artifacts — the OpenAPI YAML (Task 1) and the fixtures (Task 3) — are specified precisely (schema field lists from the cited handoff data model, the exact path set pinned by the contract test, the fixture-state checklist from spec §8) with two fully-worked path examples and the handler/fixture patterns; transcribing the entire YAML + every fixture inline would be error-prone duplication of the cited sources. Every logic file (client, hooks, query wiring, useEventSource, useRun) has complete code.

**3. Type consistency:** `apiFetch<T>`/`apiList<T>` signatures + `ApiError{message,status}` are used identically across client tests, hooks, and useRun. `Meta` shape (`total/page_size/page_number`) matches the envelope, the contract `Meta` schema, and `apiList`'s return. `queryKeys` factory names match their hook usages and the `run(id)` key used by `useRun`. Entity types are sourced uniformly from `components["schemas"][...]`. The barrel test names match the actual exports (client + queryClient + queryKeys + hooks incl. `useRun`). The status enum `[backlog,todo,in_progress,in_review,done]` is identical in the contract test, the OpenAPI doc requirement, and the spec.
