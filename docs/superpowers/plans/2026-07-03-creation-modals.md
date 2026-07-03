# Creation Modals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users create Projects and Work Items (Epic / Feature / Task) from the board UI via modals, wiring the currently no-op **New** button and board `+` affordances.

**Architecture:** A hand-rolled `Modal` primitive plus small form primitives in `components/ui/`; two React Query mutation hooks; a `CreateModalProvider` React context that owns open-state and renders the active modal; triggers in Topbar, Sidebar, and BoardView call the context. UI-only — the backend `POST /projects` and `POST /projects/{id}/work-items` endpoints and their MSW mocks already exist.

**Tech Stack:** React 18, TypeScript, @tanstack/react-query v5, react-router-dom v6, Tailwind v4, Vitest + Testing Library + MSW.

**Working directory:** all paths below are relative to `projects/ui/` in the worktree `.worktrees/creation-modals` (branch `feat/creation-modals`).

## Global Constraints

- **Immutability:** update state with `setForm(f => ({ ...f, ...changes }))`; never mutate objects/arrays in place.
- **API envelope:** all requests go through `apiPost`/`apiFetch` (they unwrap `{success,data,error}` and throw `ApiError` on failure). Never call `fetch` directly.
- **Naming:** components/types `PascalCase`; hooks `useX`; booleans `is/has/can`.
- **Files small & focused:** one responsibility per file; co-locate `*.test.tsx` beside source.
- **TDD:** write the failing test first, watch it fail, implement minimally, watch it pass, commit.
- **Types come from the OpenAPI schema:** `components["schemas"]["ProjectCreate" | "WorkItemCreate" | "Project" | "WorkItem"]` — do not hand-redefine request/response shapes.
- **Test command:** `pnpm test -- <path>` (Vitest). Run from `projects/ui/`.
- **Commit format:** `<type>: <description>` (feat/fix/refactor/docs/test/chore).

## Reference: exact schema types (already generated in `src/lib/api/schema.d.ts`)

```ts
ProjectCreate  = { name: string; repoUrl: string }
WorkItemCreate = {
  type: "epic" | "feature" | "task";
  title: string;
  status: "backlog" | "todo" | "in_progress" | "in_review" | "done";
  priority: "low" | "medium" | "high" | "urgent";
  epicId?: string;
  featureId?: string;
  spec?: string;
}
Project  = { id; name; repoUrl; itemCount; createdAt; updatedAt }
WorkItem = { id; type; title; status; priority; epicId?; featureId?; projectId; spec?; ... }
```

## Reference: existing API helpers

```ts
// src/lib/api/client.ts
apiPost = <T>(path: string, json: unknown) => Promise<T>   // POST + unwrap envelope, throws ApiError
apiList = <T>(path, params?) => Promise<{ results: T[]; meta }>
// src/lib/api/queryKeys.ts
queryKeys.projects()        // ["projects"]
queryKeys.board(projectId)  // ["board", projectId]
// board list actually rendered via useProjectWorkItems → key ["work-items","project",projectId]
```

---

## File Structure

New files (all under `projects/ui/`):

- `src/components/ui/Modal.tsx` (+ `Modal.test.tsx`) — overlay + panel primitive.
- `src/components/ui/FormField.tsx` (+ test) — label + control + error wrapper.
- `src/components/ui/TextInput.tsx` — styled `<input>`.
- `src/components/ui/Textarea.tsx` — styled `<textarea>`.
- `src/components/ui/Select.tsx` — styled `<select>`.
- `src/components/ui/FormControls.test.tsx` — tests for TextInput/Textarea/Select.
- `src/lib/api/hooks/useCreateProject.ts` (+ `.test.tsx`).
- `src/lib/api/hooks/useCreateWorkItem.ts` (+ `.test.tsx`).
- `src/lib/hooks/useCurrentProjectId.ts` — resolves the active project id for the New button.
- `src/modules/create/CreateProjectModal.tsx` (+ test).
- `src/modules/create/CreateWorkItemModal.tsx` (+ test).
- `src/modules/create/CreateModalProvider.tsx` (+ test) — context + renders active modal.
- `src/modules/create/useCreateModal.ts` — context hook.

Modified files:

- `src/components/ui/index.ts` — export new primitives.
- `src/lib/api/hooks/index.ts` — export new hooks.
- `src/app/AppShell.tsx` — wrap in provider; wire `onNew`.
- `src/app/Sidebar.tsx` — Create Project `+` in the PROJECTS header.
- `src/modules/board/BoardView.tsx` — column `+` + empty-state CTA call the context.

---

## Task 1: `Modal` primitive

**Files:**
- Create: `src/components/ui/Modal.tsx`
- Test: `src/components/ui/Modal.test.tsx`
- Modify: `src/components/ui/index.ts`

**Interfaces:**
- Produces: `Modal({ title: string; onClose: () => void; footer?: ReactNode; children: ReactNode })`. Renders a fixed overlay + centered panel; closes on Esc, overlay click, and the header ✕ button.

- [ ] **Step 1: Write the failing test**

```tsx
// src/components/ui/Modal.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Modal } from "./Modal";

test("renders title and children", () => {
  render(<Modal title="Create Project" onClose={() => {}}>body</Modal>);
  expect(screen.getByRole("dialog")).toHaveTextContent("Create Project");
  expect(screen.getByText("body")).toBeInTheDocument();
});

test("closes on Escape", async () => {
  const onClose = vi.fn();
  render(<Modal title="T" onClose={onClose}>b</Modal>);
  await userEvent.keyboard("{Escape}");
  expect(onClose).toHaveBeenCalledOnce();
});

test("closes on overlay click but not panel click", async () => {
  const onClose = vi.fn();
  render(<Modal title="T" onClose={onClose}>b</Modal>);
  await userEvent.click(screen.getByTestId("modal-overlay"));
  expect(onClose).toHaveBeenCalledOnce();
  await userEvent.click(screen.getByRole("dialog"));
  expect(onClose).toHaveBeenCalledOnce(); // unchanged
});

test("closes on the header close button", async () => {
  const onClose = vi.fn();
  render(<Modal title="T" onClose={onClose}>b</Modal>);
  await userEvent.click(screen.getByRole("button", { name: /close/i }));
  expect(onClose).toHaveBeenCalledOnce();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- src/components/ui/Modal.test.tsx`
Expected: FAIL — cannot resolve `./Modal`.

- [ ] **Step 3: Write minimal implementation**

```tsx
// src/components/ui/Modal.tsx
import { useEffect, useRef, type ReactNode } from "react";

interface ModalProps {
  title: string;
  onClose: () => void;
  footer?: ReactNode;
  children: ReactNode;
}

export function Modal({ title, onClose, footer, children }: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    panelRef.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      data-testid="modal-overlay"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-label={title}
        tabIndex={-1}
        className="w-[440px] max-w-[92vw] rounded-[8px] border border-border bg-bg-surface text-text-1 shadow-xl outline-none"
      >
        <div className="flex items-center justify-between border-b border-[rgba(255,255,255,0.06)] px-4 py-3">
          <span className="text-[13px] font-semibold">{title}</span>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="text-text-4 hover:text-text-2 text-[15px] leading-none"
          >
            ✕
          </button>
        </div>
        <div className="px-4 py-4">{children}</div>
        {footer && (
          <div className="flex items-center justify-end gap-2 border-t border-[rgba(255,255,255,0.06)] px-4 py-3">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- src/components/ui/Modal.test.tsx`
Expected: PASS (4 tests).

- [ ] **Step 5: Export from the barrel**

Add to `src/components/ui/index.ts`:

```ts
export { Modal } from "./Modal";
```

- [ ] **Step 6: Commit**

```bash
git add src/components/ui/Modal.tsx src/components/ui/Modal.test.tsx src/components/ui/index.ts
git commit -m "feat: add Modal UI primitive"
```

---

## Task 2: Form primitives (`FormField`, `TextInput`, `Textarea`, `Select`)

**Files:**
- Create: `src/components/ui/FormField.tsx`, `TextInput.tsx`, `Textarea.tsx`, `Select.tsx`
- Test: `src/components/ui/FormField.test.tsx`, `src/components/ui/FormControls.test.tsx`
- Modify: `src/components/ui/index.ts`

**Interfaces:**
- Produces:
  - `FormField({ label: string; error?: string; htmlFor?: string; children: ReactNode })`
  - `TextInput` — `InputHTMLAttributes<HTMLInputElement>` passthrough, styled.
  - `Textarea` — `TextareaHTMLAttributes<HTMLTextAreaElement>` passthrough, styled.
  - `Select` — `SelectHTMLAttributes<HTMLSelectElement>` passthrough (children = `<option>`s), styled.

- [ ] **Step 1: Write the failing tests**

```tsx
// src/components/ui/FormField.test.tsx
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { FormField } from "./FormField";

test("renders label and children", () => {
  render(<FormField label="Name"><input aria-label="Name" /></FormField>);
  expect(screen.getByText("Name")).toBeInTheDocument();
  expect(screen.getByLabelText("Name")).toBeInTheDocument();
});

test("renders error text when provided", () => {
  render(<FormField label="Name" error="Required"><input /></FormField>);
  expect(screen.getByText("Required")).toBeInTheDocument();
});
```

```tsx
// src/components/ui/FormControls.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { TextInput } from "./TextInput";
import { Textarea } from "./Textarea";
import { Select } from "./Select";

test("TextInput forwards value and change", async () => {
  const onChange = vi.fn();
  render(<TextInput aria-label="n" value="" onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("n"), "a");
  expect(onChange).toHaveBeenCalled();
});

test("Textarea renders", () => {
  render(<Textarea aria-label="spec" value="" onChange={() => {}} />);
  expect(screen.getByLabelText("spec")).toBeInTheDocument();
});

test("Select renders options and forwards change", async () => {
  const onChange = vi.fn();
  render(
    <Select aria-label="priority" value="low" onChange={onChange}>
      <option value="low">Low</option>
      <option value="high">High</option>
    </Select>,
  );
  await userEvent.selectOptions(screen.getByLabelText("priority"), "high");
  expect(onChange).toHaveBeenCalled();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pnpm test -- src/components/ui/FormField.test.tsx src/components/ui/FormControls.test.tsx`
Expected: FAIL — modules not found.

- [ ] **Step 3: Write minimal implementations**

```tsx
// src/components/ui/FormField.tsx
import type { ReactNode } from "react";

export function FormField(
  { label, error, htmlFor, children }: { label: string; error?: string; htmlFor?: string; children: ReactNode },
) {
  return (
    <label htmlFor={htmlFor} className="mb-3 flex flex-col gap-1">
      <span className="text-[11px] font-medium text-text-3">{label}</span>
      {children}
      {error && <span className="text-[10.5px] text-[#e5686b]">{error}</span>}
    </label>
  );
}
```

```tsx
// src/components/ui/TextInput.tsx
import type { InputHTMLAttributes } from "react";

export function TextInput({ className = "", ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={`h-8 rounded-[5px] border border-border bg-bg-input px-2 text-[12px] text-text-1 outline-none focus:border-accent ${className}`}
      {...rest}
    />
  );
}
```

```tsx
// src/components/ui/Textarea.tsx
import type { TextareaHTMLAttributes } from "react";

export function Textarea({ className = "", ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={`min-h-[72px] rounded-[5px] border border-border bg-bg-input px-2 py-1.5 text-[12px] text-text-1 outline-none focus:border-accent ${className}`}
      {...rest}
    />
  );
}
```

```tsx
// src/components/ui/Select.tsx
import type { SelectHTMLAttributes } from "react";

export function Select({ className = "", children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={`h-8 rounded-[5px] border border-border bg-bg-input px-2 text-[12px] text-text-1 outline-none focus:border-accent ${className}`}
      {...rest}
    >
      {children}
    </select>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pnpm test -- src/components/ui/FormField.test.tsx src/components/ui/FormControls.test.tsx`
Expected: PASS.

- [ ] **Step 5: Export from the barrel**

Add to `src/components/ui/index.ts`:

```ts
export { FormField } from "./FormField";
export { TextInput } from "./TextInput";
export { Textarea } from "./Textarea";
export { Select } from "./Select";
```

- [ ] **Step 6: Commit**

```bash
git add src/components/ui/FormField.tsx src/components/ui/TextInput.tsx src/components/ui/Textarea.tsx src/components/ui/Select.tsx src/components/ui/FormField.test.tsx src/components/ui/FormControls.test.tsx src/components/ui/index.ts
git commit -m "feat: add form field UI primitives"
```

---

## Task 3: Mutation hooks (`useCreateProject`, `useCreateWorkItem`)

**Files:**
- Create: `src/lib/api/hooks/useCreateProject.ts`, `useCreateWorkItem.ts`
- Test: `src/lib/api/hooks/useCreateProject.test.tsx`, `useCreateWorkItem.test.tsx`
- Modify: `src/lib/api/hooks/index.ts`

**Interfaces:**
- Consumes: `apiPost`, `queryKeys`, `components["schemas"]`.
- Produces:
  - `useCreateProject()` → React Query mutation; `mutateAsync(body: ProjectCreate) => Promise<Project>`; invalidates `queryKeys.projects()`.
  - `useCreateWorkItem(projectId: string)` → mutation; `mutateAsync(body: WorkItemCreate) => Promise<WorkItem>`; invalidates `["work-items","project",projectId]`, `queryKeys.board(projectId)`, `queryKeys.projects()`.

- [ ] **Step 1: Write the failing tests**

```tsx
// src/lib/api/hooks/useCreateProject.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import { server } from "../mocks/server";
import { useCreateProject } from "./useCreateProject";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

test("posts a project and resolves with the created project", async () => {
  server.use(
    http.post("/api/projects", async ({ request }) => {
      const body = (await request.json()) as { name: string; repoUrl: string };
      return HttpResponse.json(
        { success: true, error: null, data: { id: "p9", name: body.name, repoUrl: body.repoUrl, itemCount: 0, createdAt: "2026-07-03T00:00:00Z", updatedAt: "2026-07-03T00:00:00Z" } },
        { status: 201 },
      );
    }),
  );
  const { result } = renderHook(() => useCreateProject(), { wrapper });
  await act(async () => {
    await result.current.mutateAsync({ name: "New", repoUrl: "" });
  });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.id).toBe("p9");
});
```

```tsx
// src/lib/api/hooks/useCreateWorkItem.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import { server } from "../mocks/server";
import { useCreateWorkItem } from "./useCreateWorkItem";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

test("posts a work item under the project and resolves with it", async () => {
  server.use(
    http.post("/api/projects/p1/work-items", async ({ request }) => {
      const body = (await request.json()) as { type: string; title: string };
      return HttpResponse.json(
        { success: true, error: null, data: { id: "w9", type: body.type, title: body.title, status: "todo", priority: "medium", projectId: "p1", createdAt: "2026-07-03T00:00:00Z", updatedAt: "2026-07-03T00:00:00Z" } },
        { status: 201 },
      );
    }),
  );
  const { result } = renderHook(() => useCreateWorkItem("p1"), { wrapper });
  await act(async () => {
    await result.current.mutateAsync({ type: "epic", title: "E", status: "todo", priority: "medium" });
  });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.id).toBe("w9");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pnpm test -- src/lib/api/hooks/useCreateProject.test.tsx src/lib/api/hooks/useCreateWorkItem.test.tsx`
Expected: FAIL — modules not found.

- [ ] **Step 3: Write minimal implementations**

```ts
// src/lib/api/hooks/useCreateProject.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiPost } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type ProjectCreate = components["schemas"]["ProjectCreate"];
export type Project = components["schemas"]["Project"];

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProjectCreate) => apiPost<Project>("/projects", body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.projects() });
    },
  });
}
```

```ts
// src/lib/api/hooks/useCreateWorkItem.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiPost } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type WorkItemCreate = components["schemas"]["WorkItemCreate"];
export type WorkItem = components["schemas"]["WorkItem"];

export function useCreateWorkItem(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: WorkItemCreate) =>
      apiPost<WorkItem>(`/projects/${projectId}/work-items`, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["work-items", "project", projectId] });
      void qc.invalidateQueries({ queryKey: queryKeys.board(projectId) });
      void qc.invalidateQueries({ queryKey: queryKeys.projects() });
    },
  });
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pnpm test -- src/lib/api/hooks/useCreateProject.test.tsx src/lib/api/hooks/useCreateWorkItem.test.tsx`
Expected: PASS.

- [ ] **Step 5: Export from the barrel**

Add to `src/lib/api/hooks/index.ts`:

```ts
export { useCreateProject } from "./useCreateProject";
export type { ProjectCreate } from "./useCreateProject";
export { useCreateWorkItem } from "./useCreateWorkItem";
export type { WorkItemCreate } from "./useCreateWorkItem";
```

- [ ] **Step 6: Commit**

```bash
git add src/lib/api/hooks/useCreateProject.ts src/lib/api/hooks/useCreateWorkItem.ts src/lib/api/hooks/useCreateProject.test.tsx src/lib/api/hooks/useCreateWorkItem.test.tsx src/lib/api/hooks/index.ts
git commit -m "feat: add create-project and create-work-item mutation hooks"
```

---

## Task 4: `CreateProjectModal`

**Files:**
- Create: `src/modules/create/CreateProjectModal.tsx`
- Test: `src/modules/create/CreateProjectModal.test.tsx`

**Interfaces:**
- Consumes: `Modal`, `FormField`, `TextInput`, `Button` from `components/ui`; `useCreateProject` from `lib/api/hooks`.
- Produces: `CreateProjectModal({ onClose: () => void })`. Name required (submit disabled until non-empty); submits `{ name, repoUrl }`; calls `onClose` on success; shows `mutation.error.message` inline.

- [ ] **Step 1: Write the failing test**

```tsx
// src/modules/create/CreateProjectModal.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { expect, test, vi } from "vitest";
import { server } from "../../lib/api/mocks/server";
import { CreateProjectModal } from "./CreateProjectModal";

function renderModal(onClose = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <CreateProjectModal onClose={onClose} />
    </QueryClientProvider>,
  );
  return { onClose };
}

test("submit is disabled until a name is entered", async () => {
  renderModal();
  const submit = screen.getByRole("button", { name: /create project/i });
  expect(submit).toBeDisabled();
  await userEvent.type(screen.getByLabelText(/name/i), "Acme");
  expect(submit).toBeEnabled();
});

test("creates a project and closes", async () => {
  server.use(
    http.post("/api/projects", async () =>
      HttpResponse.json(
        { success: true, error: null, data: { id: "p9", name: "Acme", repoUrl: "", itemCount: 0, createdAt: "2026-07-03T00:00:00Z", updatedAt: "2026-07-03T00:00:00Z" } },
        { status: 201 },
      ),
    ),
  );
  const { onClose } = renderModal();
  await userEvent.type(screen.getByLabelText(/name/i), "Acme");
  await userEvent.click(screen.getByRole("button", { name: /create project/i }));
  await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- src/modules/create/CreateProjectModal.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```tsx
// src/modules/create/CreateProjectModal.tsx
import { useState } from "react";
import { Button, FormField, Modal, TextInput } from "../../components/ui";
import { useCreateProject } from "../../lib/api/hooks";

export function CreateProjectModal({ onClose }: { onClose: () => void }) {
  const [form, setForm] = useState({ name: "", repoUrl: "" });
  const mutation = useCreateProject();
  const canSubmit = form.name.trim().length > 0 && !mutation.isPending;

  async function submit() {
    await mutation.mutateAsync({ name: form.name.trim(), repoUrl: form.repoUrl.trim() });
    onClose();
  }

  return (
    <Modal
      title="Create Project"
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            disabled={!canSubmit}
            onClick={() => { void submit(); }}
          >
            {mutation.isPending ? "Creating…" : "Create Project"}
          </Button>
        </>
      }
    >
      <FormField label="Name">
        <TextInput
          aria-label="Name"
          value={form.name}
          onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          autoFocus
        />
      </FormField>
      <FormField label="Repo URL">
        <TextInput
          aria-label="Repo URL"
          value={form.repoUrl}
          placeholder="https://github.com/org/repo"
          onChange={(e) => setForm((f) => ({ ...f, repoUrl: e.target.value }))}
        />
      </FormField>
      {mutation.isError && (
        <p className="text-[10.5px] text-[#e5686b]">{(mutation.error as Error).message}</p>
      )}
    </Modal>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- src/modules/create/CreateProjectModal.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/modules/create/CreateProjectModal.tsx src/modules/create/CreateProjectModal.test.tsx
git commit -m "feat: add Create Project modal"
```

---

## Task 5: `CreateWorkItemModal`

**Files:**
- Create: `src/modules/create/CreateWorkItemModal.tsx`
- Test: `src/modules/create/CreateWorkItemModal.test.tsx`

**Interfaces:**
- Consumes: `Modal`, `FormField`, `TextInput`, `Textarea`, `Select`, `Chip`, `Button` from `components/ui`; `useCreateWorkItem` from `lib/api/hooks`; `useProjectWorkItems` from `../board/useProjectWorkItems`.
- Produces: `CreateWorkItemModal({ projectId: string; initialStatus?: WorkItem["status"]; onClose: () => void })`.
  - Type tabs Epic / Feature / Task (default Task). Adaptive fields:
    - Epic: Status, Priority, Spec.
    - Feature: + Parent Epic (from epics in project).
    - Task: + Parent Epic + Parent Feature (from features in project).
  - Footer: **Create [type]** (submit → onClose), **Create & add another** (submit → reset title+spec, keep type/parents/status/priority), **Cancel**.
  - Body sent: `{ type, title, status, priority, spec?, epicId?, featureId? }` — parent ids included only when set and relevant to the type.

**Notes for the implementer:**
- `useProjectWorkItems(projectId)` returns `{ data: { results: WorkItem[] } }`. Filter `results` by `type === "epic"` / `type === "feature"`.
- Title is required (submit disabled until non-empty).
- Keep helper `buildBody(form)` pure (returns a new object).

- [ ] **Step 1: Write the failing test**

```tsx
// src/modules/create/CreateWorkItemModal.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { expect, test, vi } from "vitest";
import { server } from "../../lib/api/mocks/server";
import { CreateWorkItemModal } from "./CreateWorkItemModal";

function renderModal(props: Partial<{ initialStatus: "todo"; onClose: () => void }> = {}) {
  const onClose = props.onClose ?? vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  // no work items in the project by default
  server.use(
    http.get("/api/work-items", () =>
      HttpResponse.json({ success: true, error: null, data: [], meta: { total: 0, page_size: 50, page_number: 1 } }),
    ),
  );
  render(
    <QueryClientProvider client={qc}>
      <CreateWorkItemModal projectId="p1" initialStatus={props.initialStatus} onClose={onClose} />
    </QueryClientProvider>,
  );
  return { onClose };
}

test("defaults to Task and shows parent feature + epic selects", async () => {
  renderModal();
  expect(screen.getByRole("button", { name: /^create task$/i })).toBeInTheDocument();
  expect(screen.getByLabelText(/parent epic/i)).toBeInTheDocument();
  expect(screen.getByLabelText(/parent feature/i)).toBeInTheDocument();
});

test("switching to Epic hides parent selects", async () => {
  renderModal();
  await userEvent.click(screen.getByRole("button", { name: /^epic$/i }));
  expect(screen.queryByLabelText(/parent epic/i)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /^create epic$/i })).toBeInTheDocument();
});

test("title is required before submit", async () => {
  renderModal();
  expect(screen.getByRole("button", { name: /^create task$/i })).toBeDisabled();
  await userEvent.type(screen.getByLabelText(/title/i), "Do it");
  expect(screen.getByRole("button", { name: /^create task$/i })).toBeEnabled();
});

test("creates a work item and closes", async () => {
  server.use(
    http.post("/api/projects/p1/work-items", async ({ request }) => {
      const body = (await request.json()) as { type: string; title: string; status: string };
      expect(body.type).toBe("epic");
      expect(body.status).toBe("todo");
      return HttpResponse.json(
        { success: true, error: null, data: { id: "w9", type: "epic", title: body.title, status: "todo", priority: "medium", projectId: "p1", createdAt: "2026-07-03T00:00:00Z", updatedAt: "2026-07-03T00:00:00Z" } },
        { status: 201 },
      );
    }),
  );
  const { onClose } = renderModal({ initialStatus: "todo" });
  await userEvent.click(screen.getByRole("button", { name: /^epic$/i }));
  await userEvent.type(screen.getByLabelText(/title/i), "Big epic");
  await userEvent.click(screen.getByRole("button", { name: /^create epic$/i }));
  await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
});

test("Create & add another keeps the modal open and clears the title", async () => {
  server.use(
    http.post("/api/projects/p1/work-items", async () =>
      HttpResponse.json(
        { success: true, error: null, data: { id: "w9", type: "task", title: "t", status: "todo", priority: "medium", projectId: "p1", createdAt: "2026-07-03T00:00:00Z", updatedAt: "2026-07-03T00:00:00Z" } },
        { status: 201 },
      ),
    ),
  );
  const { onClose } = renderModal();
  await userEvent.type(screen.getByLabelText(/title/i), "First");
  await userEvent.click(screen.getByRole("button", { name: /create & add another/i }));
  await waitFor(() => expect((screen.getByLabelText(/title/i) as HTMLInputElement).value).toBe(""));
  expect(onClose).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- src/modules/create/CreateWorkItemModal.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Write minimal implementation**

```tsx
// src/modules/create/CreateWorkItemModal.tsx
import { useState } from "react";
import { Button, Chip, FormField, Modal, Select, Textarea, TextInput } from "../../components/ui";
import { useCreateWorkItem, type WorkItemCreate } from "../../lib/api/hooks";
import { useProjectWorkItems } from "../board/useProjectWorkItems";

type Kind = "epic" | "feature" | "task";
type Status = WorkItemCreate["status"];
type Priority = WorkItemCreate["priority"];

const KIND_LABELS: Record<Kind, string> = { epic: "Epic", feature: "Feature", task: "Task" };
const STATUSES: Status[] = ["backlog", "todo", "in_progress", "in_review", "done"];
const PRIORITIES: Priority[] = ["low", "medium", "high", "urgent"];

interface Props {
  projectId: string;
  initialStatus?: Status;
  onClose: () => void;
}

interface FormState {
  type: Kind;
  title: string;
  status: Status;
  priority: Priority;
  epicId: string;
  featureId: string;
  spec: string;
}

function buildBody(form: FormState): WorkItemCreate {
  const body: WorkItemCreate = {
    type: form.type,
    title: form.title.trim(),
    status: form.status,
    priority: form.priority,
  };
  if (form.spec.trim()) body.spec = form.spec.trim();
  if (form.type !== "epic" && form.epicId) body.epicId = form.epicId;
  if (form.type === "task" && form.featureId) body.featureId = form.featureId;
  return body;
}

export function CreateWorkItemModal({ projectId, initialStatus, onClose }: Props) {
  const [form, setForm] = useState<FormState>({
    type: "task",
    title: "",
    status: initialStatus ?? "todo",
    priority: "medium",
    epicId: "",
    featureId: "",
    spec: "",
  });
  const mutation = useCreateWorkItem(projectId);
  const { data } = useProjectWorkItems(projectId);
  const items = data?.results ?? [];
  const epics = items.filter((i) => i.type === "epic");
  const features = items.filter((i) => i.type === "feature");
  const canSubmit = form.title.trim().length > 0 && !mutation.isPending;

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function submit(addAnother: boolean) {
    await mutation.mutateAsync(buildBody(form));
    if (addAnother) {
      setForm((f) => ({ ...f, title: "", spec: "" }));
    } else {
      onClose();
    }
  }

  return (
    <Modal
      title="Create Work Item"
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button variant="secondary" disabled={!canSubmit} onClick={() => { void submit(true); }}>
            Create &amp; add another
          </Button>
          <Button variant="primary" disabled={!canSubmit} onClick={() => { void submit(false); }}>
            {mutation.isPending ? "Creating…" : `Create ${KIND_LABELS[form.type]}`}
          </Button>
        </>
      }
    >
      <div className="mb-3 flex gap-1">
        {(Object.keys(KIND_LABELS) as Kind[]).map((k) => (
          <Chip key={k} active={form.type === k} onClick={() => set("type", k)}>
            {KIND_LABELS[k]}
          </Chip>
        ))}
      </div>

      <FormField label="Title">
        <TextInput
          aria-label="Title"
          value={form.title}
          onChange={(e) => set("title", e.target.value)}
          autoFocus
        />
      </FormField>

      <div className="flex gap-3">
        <div className="flex-1">
          <FormField label="Status">
            <Select aria-label="Status" value={form.status} onChange={(e) => set("status", e.target.value as Status)}>
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </Select>
          </FormField>
        </div>
        <div className="flex-1">
          <FormField label="Priority">
            <Select aria-label="Priority" value={form.priority} onChange={(e) => set("priority", e.target.value as Priority)}>
              {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
            </Select>
          </FormField>
        </div>
      </div>

      {form.type !== "epic" && (
        <FormField label="Parent Epic">
          <Select aria-label="Parent Epic" value={form.epicId} onChange={(e) => set("epicId", e.target.value)}>
            <option value="">None</option>
            {epics.map((e) => <option key={e.id} value={e.id}>{e.title}</option>)}
          </Select>
        </FormField>
      )}

      {form.type === "task" && (
        <FormField label="Parent Feature">
          <Select aria-label="Parent Feature" value={form.featureId} onChange={(e) => set("featureId", e.target.value)}>
            <option value="">None</option>
            {features.map((f) => <option key={f.id} value={f.id}>{f.title}</option>)}
          </Select>
        </FormField>
      )}

      <FormField label="Spec / Description">
        <Textarea aria-label="Spec / Description" value={form.spec} onChange={(e) => set("spec", e.target.value)} />
      </FormField>

      {mutation.isError && (
        <p className="text-[10.5px] text-[#e5686b]">{(mutation.error as Error).message}</p>
      )}
    </Modal>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- src/modules/create/CreateWorkItemModal.test.tsx`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/modules/create/CreateWorkItemModal.tsx src/modules/create/CreateWorkItemModal.test.tsx
git commit -m "feat: add Create Work Item modal with type-adaptive fields"
```

---

## Task 6: `CreateModalProvider` + `useCreateModal`

**Files:**
- Create: `src/modules/create/useCreateModal.ts`, `src/modules/create/CreateModalProvider.tsx`
- Test: `src/modules/create/CreateModalProvider.test.tsx`

**Interfaces:**
- Produces:
  - Context value `CreateModalContextValue = { openCreateProject: () => void; openCreateWorkItem: (o: { projectId: string; status?: WorkItem["status"] }) => void; close: () => void }`.
  - `CreateModalProvider({ children })` — holds state, renders `CreateProjectModal` / `CreateWorkItemModal` when open, provides the value.
  - `useCreateModal(): CreateModalContextValue` — throws if used outside the provider.

- [ ] **Step 1: Write the failing test**

```tsx
// src/modules/create/CreateModalProvider.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import { server } from "../../lib/api/mocks/server";
import { CreateModalProvider } from "./CreateModalProvider";
import { useCreateModal } from "./useCreateModal";

function Harness() {
  const { openCreateProject, openCreateWorkItem } = useCreateModal();
  return (
    <>
      <button onClick={() => openCreateProject()}>open project</button>
      <button onClick={() => openCreateWorkItem({ projectId: "p1" })}>open item</button>
    </>
  );
}

function renderProvider() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  server.use(
    http.get("/api/work-items", () =>
      HttpResponse.json({ success: true, error: null, data: [], meta: { total: 0, page_size: 50, page_number: 1 } }),
    ),
  );
  render(
    <QueryClientProvider client={qc}>
      <CreateModalProvider>
        <Harness />
      </CreateModalProvider>
    </QueryClientProvider>,
  );
}

test("opens the Create Project modal", async () => {
  renderProvider();
  await userEvent.click(screen.getByText("open project"));
  expect(screen.getByRole("dialog")).toHaveTextContent("Create Project");
});

test("opens the Create Work Item modal", async () => {
  renderProvider();
  await userEvent.click(screen.getByText("open item"));
  expect(screen.getByRole("dialog")).toHaveTextContent("Create Work Item");
});

test("closing the modal removes it", async () => {
  renderProvider();
  await userEvent.click(screen.getByText("open project"));
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- src/modules/create/CreateModalProvider.test.tsx`
Expected: FAIL — modules not found.

- [ ] **Step 3: Write minimal implementations**

```ts
// src/modules/create/useCreateModal.ts
import { createContext, useContext } from "react";
import type { WorkItem } from "../../lib/api/hooks/useCreateWorkItem";

export interface CreateModalContextValue {
  openCreateProject: () => void;
  openCreateWorkItem: (o: { projectId: string; status?: WorkItem["status"] }) => void;
  close: () => void;
}

export const CreateModalContext = createContext<CreateModalContextValue | null>(null);

export function useCreateModal(): CreateModalContextValue {
  const ctx = useContext(CreateModalContext);
  if (!ctx) throw new Error("useCreateModal must be used within CreateModalProvider");
  return ctx;
}
```

```tsx
// src/modules/create/CreateModalProvider.tsx
import { useMemo, useState, type ReactNode } from "react";
import type { WorkItem } from "../../lib/api/hooks/useCreateWorkItem";
import { CreateProjectModal } from "./CreateProjectModal";
import { CreateWorkItemModal } from "./CreateWorkItemModal";
import { CreateModalContext } from "./useCreateModal";

type State =
  | { kind: "none" }
  | { kind: "project" }
  | { kind: "work-item"; projectId: string; status?: WorkItem["status"] };

export function CreateModalProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ kind: "none" });

  const value = useMemo(
    () => ({
      openCreateProject: () => setState({ kind: "project" }),
      openCreateWorkItem: (o: { projectId: string; status?: WorkItem["status"] }) =>
        setState({ kind: "work-item", projectId: o.projectId, status: o.status }),
      close: () => setState({ kind: "none" }),
    }),
    [],
  );

  const close = () => setState({ kind: "none" });

  return (
    <CreateModalContext.Provider value={value}>
      {children}
      {state.kind === "project" && <CreateProjectModal onClose={close} />}
      {state.kind === "work-item" && (
        <CreateWorkItemModal projectId={state.projectId} initialStatus={state.status} onClose={close} />
      )}
    </CreateModalContext.Provider>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- src/modules/create/CreateModalProvider.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/modules/create/useCreateModal.ts src/modules/create/CreateModalProvider.tsx src/modules/create/CreateModalProvider.test.tsx
git commit -m "feat: add CreateModalProvider context and modal host"
```

---

## Task 7: Wire the Topbar New button (AppShell) + `useCurrentProjectId`

**Files:**
- Create: `src/lib/hooks/useCurrentProjectId.ts`, `src/lib/hooks/useCurrentProjectId.test.tsx`
- Modify: `src/app/AppShell.tsx`

**Interfaces:**
- Consumes: `useProjects`, `useSearchParams`/`useParams` from react-router, `useCreateModal`.
- Produces: `useCurrentProjectId(): string | undefined` — returns the route `:projectId` (detail route) → else `?project=` search param → else the first project's id.

**Behavior:** In `AppShell`, wrap the layout in `CreateModalProvider`. Split out an inner component (so it can call `useCreateModal`, which must run inside the provider). The New button:
- opens Create Work Item seeded with the current project when one exists;
- falls back to Create Project when there is no current project (can't add items without a project).

- [ ] **Step 1: Write the failing test for `useCurrentProjectId`**

```tsx
// src/lib/hooks/useCurrentProjectId.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import { server } from "../api/mocks/server";
import { useCurrentProjectId } from "./useCurrentProjectId";

function wrapper(initialEntries: string[]) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return (
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

test("prefers the ?project= search param", async () => {
  server.use(
    http.get("/api/projects", () =>
      HttpResponse.json({ success: true, error: null, data: [{ id: "p1", name: "A", repoUrl: "", itemCount: 0, createdAt: "x", updatedAt: "x" }], meta: { total: 1, page_size: 50, page_number: 1 } }),
    ),
  );
  const { result } = renderHook(() => useCurrentProjectId(), { wrapper: wrapper(["/projects?project=pX"]) });
  await waitFor(() => expect(result.current).toBe("pX"));
});

test("falls back to the first project", async () => {
  server.use(
    http.get("/api/projects", () =>
      HttpResponse.json({ success: true, error: null, data: [{ id: "p1", name: "A", repoUrl: "", itemCount: 0, createdAt: "x", updatedAt: "x" }], meta: { total: 1, page_size: 50, page_number: 1 } }),
    ),
  );
  const { result } = renderHook(() => useCurrentProjectId(), { wrapper: wrapper(["/projects"]) });
  await waitFor(() => expect(result.current).toBe("p1"));
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm test -- src/lib/hooks/useCurrentProjectId.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `useCurrentProjectId`**

```ts
// src/lib/hooks/useCurrentProjectId.ts
import { useParams, useSearchParams } from "react-router-dom";
import { useProjects } from "../api/hooks";

export function useCurrentProjectId(): string | undefined {
  const { projectId } = useParams<{ projectId?: string }>();
  const [params] = useSearchParams();
  const { data } = useProjects();
  return projectId ?? params.get("project") ?? data?.results[0]?.id;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm test -- src/lib/hooks/useCurrentProjectId.test.tsx`
Expected: PASS.

- [ ] **Step 5: Update the existing AppShell test for the new wiring**

Open `src/app/AppShell.test.tsx`. If it renders `AppShell` directly, ensure the render is wrapped by a `QueryClientProvider` and a router (check the existing setup and match it). Add one behavior test:

```tsx
// add inside src/app/AppShell.test.tsx (adapt imports to the file's existing helpers)
import userEvent from "@testing-library/user-event";
import { screen } from "@testing-library/react";
// ... within the existing describe/render harness that mounts <AppShell/> with providers:
test("New button opens the Create Work Item modal", async () => {
  // render AppShell via the file's existing helper (providers + MemoryRouter at /projects)
  await userEvent.click(screen.getByRole("button", { name: /new/i }));
  expect(await screen.findByRole("dialog")).toHaveTextContent("Create Work Item");
});
```

> If `AppShell.test.tsx` currently renders without a QueryClient/router, extend its harness to match `App.integration.test.tsx` (which mounts the full app with providers). Reuse that harness rather than inventing a new one.

- [ ] **Step 6: Run it to verify it fails**

Run: `pnpm test -- src/app/AppShell.test.tsx`
Expected: FAIL — no dialog appears (New is still a no-op).

- [ ] **Step 7: Modify `AppShell.tsx`**

Replace the component with a provider wrapper + inner layout that wires `onNew`:

```tsx
// src/app/AppShell.tsx  (full replacement)
import { Outlet, useLocation, useSearchParams } from "react-router-dom";
import { CreateModalProvider } from "../modules/create/CreateModalProvider";
import { useCreateModal } from "../modules/create/useCreateModal";
import { useCurrentProjectId } from "../lib/hooks/useCurrentProjectId";
import { ChatPanel } from "./ChatPanel";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

type View = "board" | "list";

function isView(v: string | null): v is View {
  return v === "board" || v === "list";
}

const ROUTE_TITLES: Record<string, string> = {
  "/dashboard": "Dashboard",
  "/inbox": "Inbox",
  "/projects": "Projects",
  "/settings/agents": "Settings",
};

function usePageTitle(): string {
  const { pathname } = useLocation();
  if (ROUTE_TITLES[pathname]) return ROUTE_TITLES[pathname];
  if (pathname.startsWith("/projects/")) return "Projects";
  return "Projects";
}

function AppShellLayout() {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawView = searchParams.get("view");
  const view: View = isView(rawView) ? rawView : "board";
  const title = usePageTitle();
  const projectId = useCurrentProjectId();
  const { openCreateProject, openCreateWorkItem } = useCreateModal();

  function handleViewChange(next: View) {
    setSearchParams((prev) => {
      const updated = new URLSearchParams(prev);
      updated.set("view", next);
      return updated;
    });
  }

  function handleNew() {
    if (projectId) openCreateWorkItem({ projectId });
    else openCreateProject();
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-bg-base text-text-1">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Topbar title={title} count={0} view={view} onViewChange={handleViewChange} onNew={handleNew} />
        <main className="flex-1 overflow-auto p-4">
          <Outlet />
        </main>
      </div>
      <ChatPanel />
    </div>
  );
}

export function AppShell() {
  return (
    <CreateModalProvider>
      <AppShellLayout />
    </CreateModalProvider>
  );
}
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pnpm test -- src/app/AppShell.test.tsx src/lib/hooks/useCurrentProjectId.test.tsx`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/app/AppShell.tsx src/app/AppShell.test.tsx src/lib/hooks/useCurrentProjectId.ts src/lib/hooks/useCurrentProjectId.test.tsx
git commit -m "feat: wire Topbar New button to creation modals"
```

---

## Task 8: Board `+` triggers, empty-state CTA, and Sidebar Create Project

**Files:**
- Modify: `src/modules/board/BoardView.tsx`, `src/modules/board/BoardView.test.tsx`
- Modify: `src/app/Sidebar.tsx`, `src/app/Sidebar.test.tsx`

**Interfaces:**
- Consumes: `useCreateModal` from `../create/useCreateModal` (BoardView) / `../modules/create/useCreateModal` (Sidebar).
- The board column `+` button (already present in `ColumnHeader`) gains an `onClick` that opens Create Work Item seeded with that column's status. The Sidebar PROJECTS header gains a `+` that opens Create Project.

**Note:** BoardView and Sidebar tests must render inside a `CreateModalProvider` (plus their existing `QueryClientProvider`/router). Add a small local `renderWithProviders` in each test if one isn't already present.

- [ ] **Step 1: Write the failing test for the board `+`**

```tsx
// add to src/modules/board/BoardView.test.tsx
import userEvent from "@testing-library/user-event";
import { screen } from "@testing-library/react";
// Using the file's existing render setup, wrap the tree in <CreateModalProvider>.
test("column + opens Create Work Item", async () => {
  // render <CreateModalProvider><BoardView projectId="p1" /></CreateModalProvider>
  // with QueryClientProvider + MSW returning some/empty items
  await userEvent.click(screen.getAllByRole("button", { name: /add .* item/i })[0]);
  expect(await screen.findByRole("dialog")).toHaveTextContent("Create Work Item");
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pnpm test -- src/modules/board/BoardView.test.tsx`
Expected: FAIL — clicking `+` does nothing / `useCreateModal` throws (not yet wrapped/wired).

- [ ] **Step 3: Modify `BoardView.tsx`**

Pass an `onAdd` handler from `BoardView` into `ColumnHeader`, and add an empty-state CTA. Changes:

```tsx
// src/modules/board/BoardView.tsx — additions
import { Button } from "../../components/ui";
import { useCreateModal } from "../create/useCreateModal";

// ColumnHeader gains an onAdd prop:
interface ColumnHeaderProps {
  status: WorkItemStatus;
  count: number;
  onAdd: () => void;
}

function ColumnHeader({ status, count, onAdd }: ColumnHeaderProps) {
  return (
    <div className="flex items-center gap-[6px] px-[12px] py-[10px]">
      <StatusCircle status={status} size={12} />
      <span className="text-[11.5px] font-semibold text-text-1 flex-1">{STATUS_LABELS[status]}</span>
      <span className="font-mono text-[9.5px] text-text-6">{count}</span>
      <button
        type="button"
        onClick={onAdd}
        aria-label={`Add ${STATUS_LABELS[status]} item`}
        className="ml-[4px] text-text-4 hover:text-text-3 text-[14px] leading-none"
      >
        +
      </button>
    </div>
  );
}

// BoardView body:
export function BoardView({ projectId }: { projectId: string }) {
  const { data } = useProjectWorkItems(projectId);
  const results = data?.results ?? [];
  const grouped = groupByStatus(results);
  const { openCreateWorkItem } = useCreateModal();

  if (results.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-text-4">
        <p className="text-[12px]">No work items yet.</p>
        <Button variant="primary" onClick={() => openCreateWorkItem({ projectId })}>
          Create your first item
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <LiveAgentsRibbon />
      <div className="flex flex-1 overflow-x-auto overflow-y-hidden">
        {STATUS_ORDER.map((status) => {
          const items = grouped[status];
          const isInProgress = status === "in_progress";
          return (
            <div
              key={status}
              className={`flex flex-col flex-1 border-r border-[rgba(255,255,255,0.05)] overflow-y-auto${isInProgress ? " bg-[#0c0d10]" : ""}`}
            >
              <ColumnHeader
                status={status}
                count={items.length}
                onAdd={() => openCreateWorkItem({ projectId, status })}
              />
              <div className="flex flex-col gap-[8px] px-[10px] pb-[10px]">
                {items.map((item) => (
                  <KanbanCard key={item.id} item={item} />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `pnpm test -- src/modules/board/BoardView.test.tsx`
Expected: PASS. (If pre-existing tests rendered `BoardView` without the provider, wrap them in `<CreateModalProvider>`.)

- [ ] **Step 5: Write the failing test for the Sidebar Create Project button**

```tsx
// add to src/app/Sidebar.test.tsx
import userEvent from "@testing-library/user-event";
import { screen } from "@testing-library/react";
// render <CreateModalProvider><MemoryRouter><Sidebar/></MemoryRouter></CreateModalProvider> with QueryClient
test("New project button opens Create Project", async () => {
  await userEvent.click(screen.getByRole("button", { name: /new project/i }));
  expect(await screen.findByRole("dialog")).toHaveTextContent("Create Project");
});
```

- [ ] **Step 6: Run it to verify it fails**

Run: `pnpm test -- src/app/Sidebar.test.tsx`
Expected: FAIL — no such button.

- [ ] **Step 7: Modify `Sidebar.tsx`**

Add the `+` button to the PROJECTS section header and wire it to the context:

```tsx
// src/app/Sidebar.tsx — additions
import { useCreateModal } from "../modules/create/useCreateModal";

// inside Sidebar(), before return:
const { openCreateProject } = useCreateModal();

// replace the PROJECTS header block:
<div className="flex items-center justify-between px-[7px] pb-[4px]">
  <span className="font-mono text-[9.5px] tracking-[0.08em] text-[#20222a]">PROJECTS</span>
  <button
    type="button"
    aria-label="New project"
    onClick={() => openCreateProject()}
    className="text-[#20222a] hover:text-[#8a8d96] text-[13px] leading-none"
  >
    +
  </button>
</div>
```

- [ ] **Step 8: Run it to verify it passes**

Run: `pnpm test -- src/app/Sidebar.test.tsx`
Expected: PASS. (Wrap any pre-existing Sidebar render in `<CreateModalProvider>` since `useCreateModal` now runs there.)

- [ ] **Step 9: Commit**

```bash
git add src/modules/board/BoardView.tsx src/modules/board/BoardView.test.tsx src/app/Sidebar.tsx src/app/Sidebar.test.tsx
git commit -m "feat: add board + and sidebar triggers for creation modals"
```

---

## Task 9: Full verification & PR

- [ ] **Step 1: Typecheck + lint + full test run**

Run from `projects/ui/`:
```bash
pnpm build       # tsc typecheck (vite build runs tsc)
pnpm lint        # if defined; otherwise skip
pnpm test        # full suite must be green
```
Expected: no type errors, all tests pass.

- [ ] **Step 2: Manual smoke (mock mode)**

```bash
pnpm dev   # VITE_USE_MOCKS=true default
```
Verify: Topbar **New** opens Create Work Item; type tabs swap fields; Create adds a card; Sidebar `+` opens Create Project; a column `+` opens the modal pre-set to that status; empty board shows the CTA.

- [ ] **Step 3: Coverage & lint gate (repo root)**

From the repo root, run the project gates referenced in `CLAUDE.md`:
```bash
make coverage    # 80% gate
make lint
```
Expected: green. (If `make` targets are backend-only, ensure `pnpm test` coverage for the UI meets the 80% bar for the new files.)

- [ ] **Step 4: Push and open the PR**

```bash
git push -u origin feat/creation-modals
gh pr create --title "feat: project & work-item creation modals" \
  --body "$(cat <<'EOF'
## Summary
- Adds a hand-rolled Modal + form primitives to the UI design system.
- Adds Create Project and Create Work Item (Epic/Feature/Task) modals with type-adaptive fields.
- Wires the Topbar New button, board column + buttons, empty-state CTA, and a Sidebar "New project" button via a CreateModalProvider context.
- New React Query mutation hooks (useCreateProject, useCreateWorkItem); backend/MSW already support the POSTs.

## Test plan
- [ ] Unit: Modal (esc/overlay/close), form primitives, both mutation hooks, both modals, provider, useCurrentProjectId.
- [ ] Wiring: Topbar New, board +, sidebar + open the right modal.
- [ ] Manual: create a project and epic/feature/task in mock mode; board refreshes.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review notes (from writing this plan)

- **Spec coverage:** Modal + form primitives (Tasks 1–2), both hooks (Task 3), Create Project modal (Task 4), Create Work Item with type tabs + Create&add-another (Task 5), provider/context (Task 6), Topbar wiring (Task 7), board `+` / empty-state / Sidebar Create Project (Task 8), verification + PR (Task 9). All spec sections mapped.
- **Assign Agent / Label** intentionally absent (spec "Out of scope").
- **Invalidation key** matches the board's real query key `["work-items","project",projectId]` (the board renders via `useProjectWorkItems`, not `useBoard`).
- **Type consistency:** `WorkItemCreate`/`ProjectCreate` come from the generated schema; `buildBody` returns a fresh object (immutability); `useCreateWorkItem(projectId)` signature is identical everywhere it's referenced.
- **Pre-existing tests:** Tasks 7–8 explicitly call out wrapping `BoardView`/`Sidebar`/`AppShell` renders in `CreateModalProvider` since `useCreateModal` now runs in those trees.
