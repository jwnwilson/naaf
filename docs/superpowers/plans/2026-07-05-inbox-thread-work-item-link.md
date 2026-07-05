# Inbox Thread → Work-Item Link Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the work-item name at the top of an inbox thread a link to that work item's detail screen.

**Architecture:** Surface `projectId` through the existing thread DTO chain (`ThreadView` → `ThreadOut`/`ThreadDetailOut` → OpenAPI yaml → generated `schema.d.ts` → mock db), then turn the plain-text `TaskBanner` in `ConversationPane` into a React-Router `<Link>` pointing at `/projects/{projectId}/items/{workItemId}`. Project-level threads (no work item) link to the project board instead.

**Tech Stack:** Python 3.12 / FastAPI / Pydantic v2 (backend), React + Vite + React Router + TanStack Query + MSW + Vitest (frontend), `openapi-typescript` for schema generation.

## Global Constraints

- Immutability: Pydantic models via `model_copy(update={...})`; never mutate.
- API envelope: every response is `{success, data, error}` (+ `meta`).
- TDD: write the failing test first; AAA structure; descriptive behavior names.
- 80% coverage gate (`make coverage`) and `make lint` must pass before PR.
- `schema.d.ts` is **generated** from `openapi/naaf-api.yaml` via `pnpm gen:api` — never hand-edit `schema.d.ts`.
- Work-item detail route is `/projects/:projectId/items/:itemId`; board route selects a project via `?project=<id>`.
- Existing work-item link pattern (reuse it): `<Link to={`/projects/${item.projectId}/items/${item.id}`}>` (`board/KanbanCard.tsx`, `board/ListRow.tsx`).

---

### Task 1: Backend — carry `project_id` on `ThreadView`

**Files:**
- Modify: `projects/server/src/domain/messaging/thread.py` (`ThreadView`, `thread_from_work_item`, `thread_from_project`)
- Test: `projects/server/tests/domain/messaging/test_thread_projection.py`

**Interfaces:**
- Consumes: `WorkItem.project_id: str`, `Project.id: str` (existing).
- Produces: `ThreadView.project_id: str`. For a work-item thread it equals `item.project_id`; for a project thread it equals `project.id`.

- [ ] **Step 1: Write the failing test**

Add to `tests/domain/messaging/test_thread_projection.py`:

```python
def test_thread_from_work_item_carries_project_id():
    view = thread_from_work_item(_item(), [])
    assert view.project_id == "p1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/domain/messaging/test_thread_projection.py::test_thread_from_work_item_carries_project_id -v`
Expected: FAIL — `AttributeError: 'ThreadView' object has no attribute 'project_id'`.

- [ ] **Step 3: Write minimal implementation**

In `domain/messaging/thread.py`, add the field to `ThreadView` (after `work_item_id`):

```python
class ThreadView(BaseModel):
    id: str  # work_item_id, or "project:<id>" for a project-level thread
    work_item_id: str
    project_id: str
    title: str
    status: str
    participants: list[str]
    participant_details: list[ThreadParticipant]
    last_message: str | None
    message_count: int
    created_at: datetime | None
```

In `thread_from_work_item`, add `project_id=item.project_id,` to the `ThreadView(...)` call (place it right after `work_item_id=item.id,`).

In `thread_from_project`, add `project_id=project.id,` to the `ThreadView(...)` call (place it right after `work_item_id="",`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd projects/server && uv run pytest tests/domain/messaging/test_thread_projection.py tests/domain/messaging/test_project_thread.py -v`
Expected: PASS (all, including the new test).

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/domain/messaging/thread.py projects/server/tests/domain/messaging/test_thread_projection.py
git commit -m "feat: carry project_id on ThreadView"
```

---

### Task 2: Backend — expose `projectId` on the thread API

**Files:**
- Modify: `projects/server/src/interactors/api/contract.py:258-268` (`ThreadOut`)
- Modify: `projects/server/src/interactors/api/routes/threads.py:46-56` (`_thread_out`)
- Test: `projects/server/tests/api/test_threads_api.py`

**Interfaces:**
- Consumes: `ThreadView.project_id` (Task 1).
- Produces: `ThreadOut.projectId: str` in the response envelope; `ThreadDetailOut` inherits it (it subclasses `ThreadOut` and is built from `_thread_out(...).model_dump()`).

- [ ] **Step 1: Write the failing test**

Add to `tests/api/test_threads_api.py` (mirrors `test_list_threads_are_work_items`, which seeds a work item in project `p1`):

```python
def test_list_threads_carry_project_id(client, session_factory):
    wid = _seed_item(session_factory)
    body = client.get("/threads").json()
    row = body["data"][0]
    assert row["projectId"] == "p1"


def test_thread_detail_carries_project_id(client, session_factory):
    wid = _seed_item(session_factory)
    body = client.get(f"/threads/{wid}").json()
    assert body["data"]["projectId"] == "p1"
```

> If the existing helper that seeds a work item is not named `_seed_item`, match the name used by `test_list_threads_are_work_items` at the top of this file and reuse it verbatim.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/server && uv run pytest tests/api/test_threads_api.py::test_list_threads_carry_project_id tests/api/test_threads_api.py::test_thread_detail_carries_project_id -v`
Expected: FAIL — `KeyError: 'projectId'`.

- [ ] **Step 3: Write minimal implementation**

In `contract.py`, add `projectId` to `ThreadOut` (right after `workItemId`):

```python
class ThreadOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str  # == workItemId
    workItemId: str
    projectId: str
    title: str
    status: str
    lastMessage: str | None = None
    messageCount: int = 0
    participants: list[str] = []
    createdAt: str
```

In `routes/threads.py`, map it in `_thread_out` (add after `workItemId=view.work_item_id,`):

```python
def _thread_out(view: ThreadView) -> ThreadOut:
    return ThreadOut(
        id=view.id,
        workItemId=view.work_item_id,
        projectId=view.project_id,
        title=view.title,
        status=view.status,
        lastMessage=view.last_message,
        messageCount=view.message_count,
        participants=view.participants,
        createdAt=iso(view.created_at),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd projects/server && uv run pytest tests/api/test_threads_api.py tests/api/test_project_thread_api.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add projects/server/src/interactors/api/contract.py projects/server/src/interactors/api/routes/threads.py projects/server/tests/api/test_threads_api.py
git commit -m "feat: expose projectId on the thread API"
```

---

### Task 3: Frontend contract — add `projectId` to the OpenAPI Thread schema and regenerate types

**Files:**
- Modify: `projects/ui/openapi/naaf-api.yaml:781-794` (`Thread` schema)
- Generate: `projects/ui/src/lib/api/schema.d.ts` (via `pnpm gen:api` — do not hand-edit)
- Test: `projects/ui/openapi/contract.test.ts`

**Interfaces:**
- Produces: generated type `components["schemas"]["Thread"]` gains a required `projectId: string`. Consumed by `useThread`/`useThreads` types and the mock db (Tasks 4–5).

- [ ] **Step 1: Write the failing test**

Add to `openapi/contract.test.ts` (follow the file's existing `parse`/`doc` style — `doc` holds the parsed yaml):

```ts
it("Thread carries a required projectId string", () => {
  const thread = doc.components.schemas.Thread;
  expect(thread.required).toContain("projectId");
  expect(thread.properties.projectId).toEqual({ type: "string" });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm vitest run openapi/contract.test.ts`
Expected: FAIL — `projectId` not in `required`.

- [ ] **Step 3: Edit the yaml, then regenerate types**

In `openapi/naaf-api.yaml`, update the `Thread` schema:
- Add `projectId` to the `required` list: `required: [id, workItemId, projectId, title, status, messageCount, participants, createdAt]`
- Add the property under `properties` (right after `workItemId: { type: string }`): `projectId: { type: string }`

Then regenerate the TypeScript types:

Run: `cd projects/ui && pnpm gen:api`
Expected: `src/lib/api/schema.d.ts` now shows `projectId: string;` inside the `Thread` schema block.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd projects/ui && pnpm vitest run openapi/contract.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add projects/ui/openapi/naaf-api.yaml projects/ui/openapi/contract.test.ts projects/ui/src/lib/api/schema.d.ts
git commit -m "feat: add projectId to the Thread OpenAPI schema"
```

---

### Task 4: Frontend mocks — populate `projectId` in seed threads and mock db

**Files:**
- Modify: `projects/ui/src/lib/api/mocks/fixtures/index.ts:421-442` (seed `threads`)
- Modify: `projects/ui/src/lib/api/mocks/db.ts:108-133` (`threadDetail` implicit-thread branch)
- Test: `projects/ui/src/lib/api/mocks/handlers.test.ts` (or the nearest existing mock-db test file)

**Interfaces:**
- Consumes: generated `Thread.projectId` (Task 3); `workItems[].projectId` (already in the mock db).
- Produces: mock `/threads` and `/threads/{id}` responses that include `projectId`.

Note: after Task 3, `schema.d.ts` requires `projectId` on `Thread`, so the seed `threads` array and the `threadDetail` implicit-thread object will fail typecheck until updated — this task makes them compile again and asserts the value.

- [ ] **Step 1: Write the failing test**

Add to `src/lib/api/mocks/handlers.test.ts` (reuse the file's existing render/fetch helpers; if a closer mock-db test exists, add it there):

```ts
it("thread detail includes the work item's projectId", async () => {
  const res = await fetch("/api/threads/wi-task-3");
  const body = await res.json();
  expect(body.data.projectId).toBeTruthy();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm vitest run src/lib/api/mocks/handlers.test.ts`
Expected: FAIL — `projectId` is `undefined`.

- [ ] **Step 3: Write minimal implementation**

In `fixtures/index.ts`, add `projectId` to each seed thread. Set it to the `projectId` of the work item the thread belongs to (look up `wi-task-3` / `wi-task-4` in the `workItems` fixture and copy their `projectId`). For example:

```ts
const threads: Thread[] = [
  {
    id: "wi-task-3",
    workItemId: "wi-task-3",
    projectId: "proj-1",   // ← match wi-task-3's projectId in the workItems fixture
    title: "Implement Docker sandbox container",
    status: "in_progress",
    lastMessage: "I've analysed the codebase. Plan: 1) Create a Docker image...",
    messageCount: 3,
    participants: ["agent-1", "user"],
    createdAt: "2026-06-29T13:00:00Z",
  },
  {
    id: "wi-task-4",
    workItemId: "wi-task-4",
    projectId: "proj-1",   // ← match wi-task-4's projectId in the workItems fixture
    title: "Implement network egress proxy",
    status: "in_progress",
    lastMessage: "Please make sure the allowlist is loaded from config.",
    messageCount: 2,
    participants: ["agent-3", "user"],
    createdAt: "2026-06-28T16:00:00Z",
  },
];
```

> Verify the exact `projectId` values by grepping the `workItems` fixture: `grep -n "wi-task-3\|wi-task-4" src/lib/api/mocks/fixtures/index.ts` and reading the `projectId` on those items. Use those literal values, not `"proj-1"` if it differs.

In `db.ts`, add `projectId` to the implicit-thread object returned by `threadDetail` (the branch that builds a thread from a work item when no seed row exists), sourced from the work item:

```ts
    return {
      id: workItemId,
      workItemId,
      projectId: item.projectId,
      title: item.title,
      status: item.status,
      lastMessage: msgs.length ? msgs[msgs.length - 1].content : null,
      messageCount: msgs.length,
      participants: details.map((p) => p.role),
      createdAt: item.createdAt ?? new Date(0).toISOString(),
      participantDetails: details,
      filesWritten,
    };
```

(The seeded-row branch spreads `...base`, which now carries `projectId` from the fixture — no change needed there.)

- [ ] **Step 4: Run tests + typecheck to verify they pass**

Run: `cd projects/ui && pnpm vitest run src/lib/api/mocks/handlers.test.ts && pnpm tsc --noEmit`
Expected: PASS and no type errors.

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/lib/api/mocks/fixtures/index.ts projects/ui/src/lib/api/mocks/db.ts projects/ui/src/lib/api/mocks/handlers.test.ts
git commit -m "feat: populate projectId in mock threads"
```

---

### Task 5: Frontend — make the inbox banner a link to the work item

**Files:**
- Modify: `projects/ui/src/modules/inbox/ConversationPane.tsx`
- Test: `projects/ui/src/modules/inbox/ConversationPane.test.tsx`

**Interfaces:**
- Consumes: `useThread(threadId)` → `ThreadDetail` with `projectId`, `workItemId`, `title` (Tasks 1–4).
- Produces: the banner renders a `react-router-dom` `<Link>`:
  - work-item thread → `/projects/{projectId}/items/{workItemId}`
  - project thread (empty `workItemId`) → `/projects?project={projectId}`
  - missing `projectId` → plain text, no link.

Note: adding a `<Link>` means `ConversationPane` now requires a router in tests. Step 1 updates `renderPane` to wrap in `MemoryRouter`; the two existing tests keep passing through that wrapper.

- [ ] **Step 1: Write the failing test**

Update `ConversationPane.test.tsx`. Change the imports and `renderPane` to provide a router, and add two assertions:

```ts
import { MemoryRouter } from "react-router-dom";
// ...existing imports...

function renderPane(threadId: string) {
  render(
    <MemoryRouter>
      <QueryClientProvider client={createQueryClient()}>
        <ConversationPane threadId={threadId} />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}
```

Add a new test:

```ts
it("links the work-item title to its detail screen", async () => {
  server.use(
    http.get("/api/threads/wi-task-3", () =>
      HttpResponse.json({
        success: true,
        data: {
          id: "wi-task-3",
          workItemId: "wi-task-3",
          projectId: "proj-1",
          title: "Implement Docker sandbox container",
          status: "in_progress",
          lastMessage: null,
          messageCount: 0,
          participants: [],
          createdAt: "2026-06-29T13:00:00Z",
          filesWritten: [],
          participantDetails: [],
        },
        error: null,
        meta: null,
      }),
    ),
    http.get("/api/threads/wi-task-3/messages", () =>
      HttpResponse.json({ success: true, data: [], error: null, meta: null }),
    ),
  );
  renderPane("wi-task-3");
  const link = await screen.findByRole("link", {
    name: /Implement Docker sandbox container/,
  });
  expect(link).toHaveAttribute("href", "/projects/proj-1/items/wi-task-3");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm vitest run src/modules/inbox/ConversationPane.test.tsx`
Expected: FAIL — no `link` role with that name (banner is currently a `<div>`).

- [ ] **Step 3: Write minimal implementation**

Rewrite `ConversationPane.tsx` so `TaskBanner` renders a link when it can, and falls back to plain text otherwise:

```tsx
import { Link } from "react-router-dom";
import { useThread } from "../../lib/api/hooks";
import { Thread } from "../../components/thread";

interface TaskBannerProps {
  workItemId: string;
  projectId?: string;
  title?: string;
}

function bannerHref({ workItemId, projectId }: TaskBannerProps): string | null {
  if (!projectId) return null;
  return workItemId
    ? `/projects/${projectId}/items/${workItemId}`
    : `/projects?project=${projectId}`;
}

function TaskBanner({ workItemId, projectId, title }: TaskBannerProps) {
  const href = bannerHref({ workItemId, projectId });
  const label = title ?? workItemId.slice(0, 8);
  return (
    <div
      className="shrink-0 px-4 py-2"
      style={{ borderBottom: "1px solid rgba(255,255,255,0.06)", background: "rgba(124,108,240,0.05)" }}
    >
      {href ? (
        <Link
          to={href}
          className="text-[12px] font-medium text-[#c4c5cb] truncate hover:text-[#7c6cf0] hover:underline"
        >
          {label}
        </Link>
      ) : (
        <p className="text-[12px] font-medium text-[#c4c5cb] truncate">{label}</p>
      )}
    </div>
  );
}

interface ConversationPaneProps {
  /** Now carries a work-item id (previously a thread id) */
  threadId: string;
}

export function ConversationPane({ threadId }: ConversationPaneProps) {
  const { data: thread } = useThread(threadId);
  return (
    <Thread
      workItemId={threadId}
      banner={
        <TaskBanner
          workItemId={thread?.workItemId ?? threadId}
          projectId={thread?.projectId}
          title={thread?.title}
        />
      }
    />
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd projects/ui && pnpm vitest run src/modules/inbox/ConversationPane.test.tsx`
Expected: PASS (all three tests — the two existing ones now render through `MemoryRouter`).

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/modules/inbox/ConversationPane.tsx projects/ui/src/modules/inbox/ConversationPane.test.tsx
git commit -m "feat: link the inbox thread banner to the work item"
```

---

### Task 6: Verify gates and open the PR

**Files:** none (verification + shipping).

- [ ] **Step 1: Backend coverage + lint**

Run: `cd projects/server && make coverage && make lint`
Expected: coverage ≥ 80% gate passes; lint clean.

- [ ] **Step 2: Frontend tests + typecheck + lint**

Run: `cd projects/ui && pnpm vitest run && pnpm tsc --noEmit && pnpm lint`
Expected: all green.

- [ ] **Step 3: Manual smoke (optional but recommended)**

Start the UI in mock mode (`cd projects/ui && pnpm dev`), open the inbox, confirm the thread header title is a link and clicking it navigates to the work-item detail screen. For a project thread, confirm it links to the board.

- [ ] **Step 4: Push and open the PR**

```bash
git push -u origin <branch>
gh pr create --title "feat: link inbox thread header to its work item" \
  --body "Surfaces projectId through the thread API and turns the inbox thread banner into a link to the work-item detail screen (project threads link to the board). See docs/superpowers/specs/2026-07-04-inbox-thread-work-item-link-design.md. Test plan: backend thread projection + threads API tests; frontend contract, mock db, and ConversationPane link tests; make coverage + make lint green."
```

---

## Self-Review

**Spec coverage:**
- Backend `projectId` on `ThreadView`/`ThreadOut`/`ThreadDetail` → Tasks 1–2. ✓
- Banner becomes a `<Link>` (work-item + project-thread + missing-projectId cases) → Task 5. ✓
- Schema regen + mock plumbing → Tasks 3–4. ✓
- TDD tests backend + frontend → each task leads with a failing test. ✓
- Edge cases (project thread → board; missing projectId → plain text) → Task 5 `bannerHref`. ✓
- Gates (`make coverage`, `make lint`) → Task 6. ✓

**Placeholder scan:** No TBD/TODO. Two lookups are flagged with an exact grep to resolve literal values (`projectId` of `wi-task-3`/`wi-task-4`; the `_seed_item` helper name) rather than left vague. ✓

**Type consistency:** `project_id` (snake, Python domain) → `projectId` (camel, contract/DTO/TS) is applied consistently. `ThreadView.project_id`, `ThreadOut.projectId`, `Thread.projectId` (yaml/TS), `TaskBanner` prop `projectId`, and route `/projects/{projectId}/items/{workItemId}` all align. ✓
