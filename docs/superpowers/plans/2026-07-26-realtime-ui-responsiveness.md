# Realtime UI Responsiveness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the remaining client-side latency and jitter in the realtime agent path so chat replies, run status, and the typing indicator feel instant and consistent.

**Architecture:** Backend PR #73 already moved both SSE streams (`/runs/{id}/events/stream`, `/threads|runs/{id}/activity/stream`) to an off-loop async UoW with an `is_disconnected()` poll-exit, fixing the event-loop freeze that was the main "inconsistent" driver. This plan is a **frontend-only** batch: (1) refetch the thread's messages the instant the agent's activity stream reports `final`, closing the "typing vanishes, reply arrives 2s later" gap; (2) refetch run status the instant a `run_finished` event streams, killing the ≤2s stale-"running" badge; (3) make optimistic message IDs unique; (4) share one `EventSource` per URL via a ref-counted registry so duplicate `<Thread>`/run-monitor mounts stop opening 2–4× redundant sockets; (5) surface a reconnect signal (optional/stretch).

**Tech Stack:** React 18, TypeScript, `@tanstack/react-query` v5, Vite, Vitest + `@testing-library/react`, `msw` for network mocks. Native `EventSource` for SSE.

## Global Constraints

- Package manager for the UI: `pnpm`, run from `projects/ui/`. Tests: `pnpm test` (= `vitest run`). Lint+typecheck gate: `pnpm lint` (= `eslint . && tsc --noEmit`).
- TypeScript: no `any` in app code; explicit types on exported functions; `interface`/`type` per the repo style; immutable updates (spread, never mutate).
- No `console.log` in production code.
- Commit format: `<type>: <description>` (feat/fix/refactor/perf/test/chore).
- This is a **frontend-only** change — do not touch `projects/server`. The backend contract (`AgentActivityEventOut`, `RunEventOut`, envelope shape) is fixed.
- Work happens in the worktree `.worktrees/realtime-sse-async` on branch `fix/realtime-ui-responsiveness` (already created off latest `origin/main`). Finish = push + open a PR; never merge to `main` locally.
- All new query invalidations must use the existing `queryKeys` factory (`projects/ui/src/lib/api/queryKeys.ts`) — never hand-write key arrays.

---

## File Structure

New files:
- `projects/ui/src/lib/hooks/eventSourceRegistry.ts` — module-level ref-counted `EventSource` registry (one socket per URL, fan-out to N subscribers). Owns all `EventSource` lifecycle.
- `projects/ui/src/lib/hooks/eventSourceRegistry.test.ts` — registry unit tests with a fake `EventSource`.
- `projects/ui/src/lib/api/hooks/useReplyRefetch.ts` — effect hook: on a `done` false→true edge, invalidate the thread's messages query.
- `projects/ui/src/lib/api/hooks/useReplyRefetch.test.tsx` — its tests.
- `projects/ui/src/lib/api/hooks/optimisticId.ts` — `makeOptimisticId()` helper.
- `projects/ui/src/lib/api/hooks/optimisticId.test.ts` — its tests.
- `projects/ui/src/lib/api/hooks/runFinished.ts` — pure `hasRunFinished(events)` predicate.
- `projects/ui/src/lib/api/hooks/runFinished.test.ts` — its tests.

Modified files:
- `projects/ui/src/lib/hooks/useEventSource.ts` — becomes a thin wrapper over the registry (same signature; no consumer changes).
- `projects/ui/src/lib/api/hooks/useSendMessage.ts` — use `makeOptimisticId()`.
- `projects/ui/src/components/thread/Thread.tsx` — wire `useReplyRefetch(workItemId, activity.done)`.
- `projects/ui/src/lib/api/hooks/useRun.ts` — invalidate the run query when `hasRunFinished(events)`.

Responsibility split: each concern (registry, reply-refetch, optimistic id, run-finished predicate) is its own small, independently testable module; the four existing files only gain a one-line wire-up each. This keeps every task's deliverable reviewable on its own.

---

### Task 1: Unique optimistic message IDs

**Problem:** `useSendMessage` sets `id: \`optimistic-${vars.content}\`` (`useSendMessage.ts`). Sending the same text twice before the first settles yields two messages with identical React keys (`Thread.tsx` renders `key={msg.id}`), causing a duplicate-key warning and reconciliation glitches.

**Files:**
- Create: `projects/ui/src/lib/api/hooks/optimisticId.ts`
- Create: `projects/ui/src/lib/api/hooks/optimisticId.test.ts`
- Modify: `projects/ui/src/lib/api/hooks/useSendMessage.ts`

**Interfaces:**
- Produces: `makeOptimisticId(): string` — returns a process-unique id prefixed `optimistic-`.

- [ ] **Step 1: Write the failing test**

```typescript
// projects/ui/src/lib/api/hooks/optimisticId.test.ts
import { expect, test } from "vitest";
import { makeOptimisticId } from "./optimisticId";

test("makeOptimisticId returns an optimistic-prefixed id", () => {
  expect(makeOptimisticId()).toMatch(/^optimistic-/);
});

test("makeOptimisticId returns a distinct id on every call", () => {
  const a = makeOptimisticId();
  const b = makeOptimisticId();
  expect(a).not.toBe(b);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm exec vitest run src/lib/api/hooks/optimisticId.test.ts`
Expected: FAIL — `Failed to resolve import "./optimisticId"`.

- [ ] **Step 3: Write minimal implementation**

```typescript
// projects/ui/src/lib/api/hooks/optimisticId.ts

/** A process-unique id for an optimistic (not-yet-persisted) message row. */
export function makeOptimisticId(): string {
  return `optimistic-${crypto.randomUUID()}`;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/ui && pnpm exec vitest run src/lib/api/hooks/optimisticId.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 5: Wire into `useSendMessage`**

In `projects/ui/src/lib/api/hooks/useSendMessage.ts`, add the import and replace the id line:

```typescript
import { makeOptimisticId } from "./optimisticId";
```

Change:

```typescript
      const optimistic: Message = {
        id: `optimistic-${vars.content}`,
```

to:

```typescript
      const optimistic: Message = {
        id: makeOptimisticId(),
```

- [ ] **Step 6: Verify the existing send test still passes + typecheck**

Run: `cd projects/ui && pnpm exec vitest run src/lib/api/hooks/useSendMessage.test.tsx && pnpm lint`
Expected: PASS; no type/lint errors.

- [ ] **Step 7: Commit**

```bash
git add projects/ui/src/lib/api/hooks/optimisticId.ts projects/ui/src/lib/api/hooks/optimisticId.test.ts projects/ui/src/lib/api/hooks/useSendMessage.ts
git commit -m "fix: unique optimistic message ids (avoid duplicate React keys)"
```

---

### Task 2: Instant reply refetch when the agent finishes

**Problem:** `Thread.tsx` calls `useThreadMessages(workItemId, activity.isWorking)`. When the activity stream emits `final`, `activity.isWorking` flips false — the typing bubble hides **and** the message poll slows 1500→2000ms — but the agent's reply message only surfaces on the next poll (up to 2s later). Result: the thread looks idle, then the reply pops in. `useAgentActivity` already exposes `done` (true after a `final`/`error`). Refetching messages on the `done` false→true edge collapses that gap to one network round-trip.

**Files:**
- Create: `projects/ui/src/lib/api/hooks/useReplyRefetch.ts`
- Create: `projects/ui/src/lib/api/hooks/useReplyRefetch.test.tsx`
- Modify: `projects/ui/src/components/thread/Thread.tsx`

**Interfaces:**
- Consumes: `queryKeys.threadMessages(workItemId)` from `../queryKeys`; `useQueryClient` from `@tanstack/react-query`.
- Produces: `useReplyRefetch(workItemId: string | undefined, done: boolean): void` — invalidates `threadMessages(workItemId)` exactly once each time `done` transitions from false to true.

- [ ] **Step 1: Write the failing test**

```tsx
// projects/ui/src/lib/api/hooks/useReplyRefetch.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { queryKeys } from "../queryKeys";
import { useReplyRefetch } from "./useReplyRefetch";

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const spy = vi.spyOn(qc, "invalidateQueries");
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { spy, wrapper };
}

test("invalidates thread messages when done goes false -> true", () => {
  const { spy, wrapper } = setup();
  const { rerender } = renderHook(({ done }) => useReplyRefetch("w1", done), {
    wrapper,
    initialProps: { done: false },
  });
  expect(spy).not.toHaveBeenCalled();

  rerender({ done: true });
  expect(spy).toHaveBeenCalledWith({ queryKey: queryKeys.threadMessages("w1") });
  expect(spy).toHaveBeenCalledTimes(1);
});

test("does not invalidate while done stays true (no repeated edge)", () => {
  const { spy, wrapper } = setup();
  const { rerender } = renderHook(({ done }) => useReplyRefetch("w1", done), {
    wrapper,
    initialProps: { done: true },
  });
  // First render with done=true is the initial mount, not a false->true edge.
  const callsAfterMount = spy.mock.calls.length;
  rerender({ done: true });
  expect(spy.mock.calls.length).toBe(callsAfterMount);
});

test("no-op when workItemId is undefined", () => {
  const { spy, wrapper } = setup();
  const { rerender } = renderHook(({ done }) => useReplyRefetch(undefined, done), {
    wrapper,
    initialProps: { done: false },
  });
  rerender({ done: true });
  expect(spy).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm exec vitest run src/lib/api/hooks/useReplyRefetch.test.tsx`
Expected: FAIL — `Failed to resolve import "./useReplyRefetch"`.

- [ ] **Step 3: Write minimal implementation**

```typescript
// projects/ui/src/lib/api/hooks/useReplyRefetch.ts
import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "../queryKeys";

/**
 * Refetch a thread's messages the instant an agent turn finishes.
 *
 * `done` comes from `useAgentActivity` (true after a `final`/`error` event).
 * The activity stream reports completion ~immediately, but the agent's reply
 * message only appears on the next `useThreadMessages` poll. Invalidating on
 * the false->true edge surfaces the reply in one round-trip instead of ~2s.
 */
export function useReplyRefetch(workItemId: string | undefined, done: boolean): void {
  const qc = useQueryClient();
  const prevDone = useRef(done);
  useEffect(() => {
    if (done && !prevDone.current && workItemId) {
      void qc.invalidateQueries({ queryKey: queryKeys.threadMessages(workItemId) });
    }
    prevDone.current = done;
  }, [done, workItemId, qc]);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/ui && pnpm exec vitest run src/lib/api/hooks/useReplyRefetch.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Wire into `Thread.tsx`**

In `projects/ui/src/components/thread/Thread.tsx`, add the import:

```typescript
import { useReplyRefetch } from "../../lib/api/hooks/useReplyRefetch";
```

Then, immediately after the existing `const activity = useAgentActivity({ threadId: workItemId });` line, add:

```typescript
  useReplyRefetch(workItemId, activity.done);
```

(`activity.done` is already returned by `useAgentActivity` via `reduceActivity`.)

- [ ] **Step 6: Verify Thread tests + typecheck still pass**

Run: `cd projects/ui && pnpm exec vitest run src/components/thread/Thread.test.tsx && pnpm lint`
Expected: PASS; no type/lint errors.

- [ ] **Step 7: Commit**

```bash
git add projects/ui/src/lib/api/hooks/useReplyRefetch.ts projects/ui/src/lib/api/hooks/useReplyRefetch.test.tsx projects/ui/src/components/thread/Thread.tsx
git commit -m "fix: refetch thread messages on agent turn completion (close typing->reply gap)"
```

---

### Task 3: Terminal run status the instant the run finishes

**Problem:** In `useRun`, `isStreaming` and the status badge come from the `/runs/{id}` poll (`refetchInterval: 2_000`, stops at terminal). The stream already delivers the `run_finished` event immediately, but status lags it by up to 2s, so the PulseDot/StatusBadge stays "running" after the run is actually done. Invalidate the run query as soon as a `run_finished` event streams in.

**Files:**
- Create: `projects/ui/src/lib/api/hooks/runFinished.ts`
- Create: `projects/ui/src/lib/api/hooks/runFinished.test.ts`
- Modify: `projects/ui/src/lib/api/hooks/useRun.ts`

**Interfaces:**
- Consumes: `RunEventOut` (already imported in `useRun.ts` as `components["schemas"]["RunEventOut"]`); `queryKeys.run(runId)`; `useQueryClient`.
- Produces: `hasRunFinished(events: { type: string }[]): boolean` — true iff any event's `type` is `"run_finished"`.

- [ ] **Step 1: Write the failing test**

```typescript
// projects/ui/src/lib/api/hooks/runFinished.test.ts
import { expect, test } from "vitest";
import { hasRunFinished } from "./runFinished";

test("returns false when no run_finished event is present", () => {
  expect(hasRunFinished([{ type: "log" }, { type: "stage_passed" }])).toBe(false);
});

test("returns true when a run_finished event is present", () => {
  expect(hasRunFinished([{ type: "log" }, { type: "run_finished" }])).toBe(true);
});

test("returns false for an empty list", () => {
  expect(hasRunFinished([])).toBe(false);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm exec vitest run src/lib/api/hooks/runFinished.test.ts`
Expected: FAIL — `Failed to resolve import "./runFinished"`.

- [ ] **Step 3: Write minimal implementation**

```typescript
// projects/ui/src/lib/api/hooks/runFinished.ts

/** True iff the event list contains a terminal `run_finished` event. */
export function hasRunFinished(events: { type: string }[]): boolean {
  return events.some((ev) => ev.type === "run_finished");
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/ui && pnpm exec vitest run src/lib/api/hooks/runFinished.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Wire into `useRun.ts`**

In `projects/ui/src/lib/api/hooks/useRun.ts`:

The current react import is `import { useEffect, useState } from "react";` — add `useRef` to it, and add the two new imports:

```typescript
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { hasRunFinished } from "./runFinished";
```

(The existing `useQuery` import stays — just add `useQueryClient` alongside it.)

Inside `useRun`, after `const events = mergeEventsBySeq(history, streamed);`, add an effect that refetches run status once the terminal event has arrived (guarded so it fires on the edge, not every render):

```typescript
  const qc = useQueryClient();
  const finished = hasRunFinished(events);
  const prevFinished = useRef(false);
  useEffect(() => {
    if (finished && !prevFinished.current) {
      void qc.invalidateQueries({ queryKey: queryKeys.run(runId) });
    }
    prevFinished.current = finished;
  }, [finished, runId, qc]);
```

Note: `queryKeys` and `useEffect` are already imported in this file; `useRef` and `useQueryClient` are added in the import edit above.

- [ ] **Step 6: Verify + typecheck**

Run: `cd projects/ui && pnpm exec vitest run src/lib/api/hooks && pnpm lint`
Expected: PASS; no type/lint errors.

- [ ] **Step 7: Commit**

```bash
git add projects/ui/src/lib/api/hooks/runFinished.ts projects/ui/src/lib/api/hooks/runFinished.test.ts projects/ui/src/lib/api/hooks/useRun.ts
git commit -m "fix: refresh run status immediately on run_finished event (drop <=2s stale badge)"
```

---

### Task 4: Share one EventSource per URL (ref-counted registry)

**Problem:** `useEventSource` opens a **new** `EventSource` per hook instance. `ChatPanel`'s `<Thread>` is mounted on every route AND a Detail Thread tab renders another `<Thread>` for the same thread → two identical `/activity/stream` sockets; a run monitor adds two more. React Query dedupes the message poll (shared key) but not the sockets. A module-level, ref-counted registry keyed by URL means N subscribers to the same URL share one `EventSource`, and it closes only when the last unsubscribes.

**Files:**
- Create: `projects/ui/src/lib/hooks/eventSourceRegistry.ts`
- Create: `projects/ui/src/lib/hooks/eventSourceRegistry.test.ts`
- Modify: `projects/ui/src/lib/hooks/useEventSource.ts`

**Interfaces:**
- Produces: `subscribeToEventSource(url: string, onMessage: (raw: string) => void): () => void` — registers a subscriber for `url`, creating the underlying `EventSource` on the first subscriber and closing it when the last unsubscribes. Returns an unsubscribe function. `onMessage` receives the raw `event.data` string (parsing stays in `useEventSource`).

- [ ] **Step 1: Write the failing test**

```typescript
// projects/ui/src/lib/hooks/eventSourceRegistry.test.ts
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { subscribeToEventSource } from "./eventSourceRegistry";

// Minimal fake EventSource so we can count instances + drive messages in jsdom.
class FakeEventSource {
  static instances: FakeEventSource[] = [];
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: ((e: unknown) => void) | null = null;
  closed = false;
  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }
  emit(data: string) {
    this.onmessage?.({ data });
  }
  close() {
    this.closed = true;
  }
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource as unknown as typeof EventSource);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

test("two subscribers to the same url share one EventSource", () => {
  const a = vi.fn();
  const b = vi.fn();
  subscribeToEventSource("/x", a);
  subscribeToEventSource("/x", b);
  expect(FakeEventSource.instances.length).toBe(1);

  FakeEventSource.instances[0].emit("hello");
  expect(a).toHaveBeenCalledWith("hello");
  expect(b).toHaveBeenCalledWith("hello");
});

test("socket stays open until the last subscriber unsubscribes", () => {
  const unsubA = subscribeToEventSource("/x", vi.fn());
  const unsubB = subscribeToEventSource("/x", vi.fn());
  const es = FakeEventSource.instances[0];

  unsubA();
  expect(es.closed).toBe(false);
  unsubB();
  expect(es.closed).toBe(true);
});

test("different urls get different sockets", () => {
  subscribeToEventSource("/x", vi.fn());
  subscribeToEventSource("/y", vi.fn());
  expect(FakeEventSource.instances.length).toBe(2);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm exec vitest run src/lib/hooks/eventSourceRegistry.test.ts`
Expected: FAIL — `Failed to resolve import "./eventSourceRegistry"`.

- [ ] **Step 3: Write minimal implementation**

```typescript
// projects/ui/src/lib/hooks/eventSourceRegistry.ts

type Subscriber = (raw: string) => void;

interface Entry {
  es: EventSource;
  subscribers: Set<Subscriber>;
}

const registry = new Map<string, Entry>();

/**
 * Subscribe to a server-sent-event URL, sharing one underlying EventSource
 * across all subscribers of the same URL. The socket is opened on the first
 * subscriber and closed when the last one unsubscribes. Returns an unsubscribe
 * function. Raw `event.data` strings are forwarded; callers parse.
 */
export function subscribeToEventSource(url: string, onMessage: Subscriber): () => void {
  let entry = registry.get(url);
  if (!entry) {
    const es = new EventSource(url);
    const created: Entry = { es, subscribers: new Set() };
    es.onmessage = (e: MessageEvent) => {
      for (const sub of created.subscribers) sub(e.data as string);
    };
    registry.set(url, created);
    entry = created;
  }
  entry.subscribers.add(onMessage);

  return () => {
    const current = registry.get(url);
    if (!current) return;
    current.subscribers.delete(onMessage);
    if (current.subscribers.size === 0) {
      current.es.close();
      registry.delete(url);
    }
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/ui && pnpm exec vitest run src/lib/hooks/eventSourceRegistry.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Rewrite `useEventSource` as a thin wrapper (signature unchanged)**

Replace the body of `projects/ui/src/lib/hooks/useEventSource.ts` with:

```typescript
import { useEffect, useRef } from "react";
import { subscribeToEventSource } from "./eventSourceRegistry";

export function useEventSource<T>(url: string | null, onMessage: (data: T) => void): void {
  const cb = useRef(onMessage);
  cb.current = onMessage;

  useEffect(() => {
    if (!url) return;
    // Guard: jsdom does not implement EventSource; skip in non-browser environments.
    if (typeof EventSource === "undefined") return;

    const unsubscribe = subscribeToEventSource(url, (raw) => {
      try {
        cb.current(JSON.parse(raw) as T);
      } catch {
        // Ignore malformed frames.
      }
    });
    return unsubscribe;
  }, [url]);
}
```

- [ ] **Step 6: Verify all SSE consumers still pass + typecheck**

Run: `cd projects/ui && pnpm exec vitest run src/components/thread src/lib/api/hooks && pnpm lint`
Expected: PASS; no type/lint errors. (Consumers `useRun`, `useAgentActivity` are unchanged — the signature is identical.)

- [ ] **Step 7: Commit**

```bash
git add projects/ui/src/lib/hooks/eventSourceRegistry.ts projects/ui/src/lib/hooks/eventSourceRegistry.test.ts projects/ui/src/lib/hooks/useEventSource.ts
git commit -m "perf: share one EventSource per url (dedupe redundant SSE sockets)"
```

---

### Task 5 (optional / stretch): Reconnect signal on the shared socket

**Problem:** `useEventSource` has no `onerror` handling; a dropped stream is invisible and recovery relies entirely on the browser's default reconnect. There is no "connection lost" affordance. This task adds an error hook to the registry and exposes an optional status callback so a caller *could* render a reconnecting indicator. Skip if the P0 batch is deemed enough — it is additive and non-blocking.

**Files:**
- Modify: `projects/ui/src/lib/hooks/eventSourceRegistry.ts`
- Modify: `projects/ui/src/lib/hooks/eventSourceRegistry.test.ts`

**Interfaces:**
- Produces: `subscribeToEventSource(url, onMessage, onStatus?: (status: "open" | "reconnecting") => void): () => void` — `onStatus("reconnecting")` fires on `es.onerror`, `onStatus("open")` on `es.onopen`. Existing 2-arg callers are unaffected (the third arg is optional).

- [ ] **Step 1: Write the failing test**

```typescript
// append to projects/ui/src/lib/hooks/eventSourceRegistry.test.ts
test("onStatus reports reconnecting when the socket errors", () => {
  const status = vi.fn();
  subscribeToEventSource("/z", vi.fn(), status);
  const es = FakeEventSource.instances[0];
  es.onerror?.({});
  expect(status).toHaveBeenCalledWith("reconnecting");
});
```

(Add `onopen` to `FakeEventSource` similarly: `onopen: (() => void) | null = null;`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm exec vitest run src/lib/hooks/eventSourceRegistry.test.ts`
Expected: FAIL — `status` not called / `onStatus` param does not exist.

- [ ] **Step 3: Implement — fan `onerror`/`onopen` out to per-subscriber status callbacks**

Replace `projects/ui/src/lib/hooks/eventSourceRegistry.ts` with:

```typescript
type Subscriber = (raw: string) => void;
type StatusSubscriber = (status: "open" | "reconnecting") => void;

interface Entry {
  es: EventSource;
  subscribers: Set<Subscriber>;
  statusSubscribers: Set<StatusSubscriber>;
}

const registry = new Map<string, Entry>();

/**
 * Subscribe to a server-sent-event URL, sharing one underlying EventSource
 * across all subscribers of the same URL. The socket is opened on the first
 * subscriber and closed when the last one unsubscribes. `onStatus`, when given,
 * receives "reconnecting" on socket error and "open" on (re)connect.
 */
export function subscribeToEventSource(
  url: string,
  onMessage: Subscriber,
  onStatus?: StatusSubscriber,
): () => void {
  let entry = registry.get(url);
  if (!entry) {
    const es = new EventSource(url);
    const created: Entry = { es, subscribers: new Set(), statusSubscribers: new Set() };
    es.onmessage = (e: MessageEvent) => {
      for (const sub of created.subscribers) sub(e.data as string);
    };
    es.onerror = () => {
      for (const sub of created.statusSubscribers) sub("reconnecting");
    };
    es.onopen = () => {
      for (const sub of created.statusSubscribers) sub("open");
    };
    registry.set(url, created);
    entry = created;
  }
  entry.subscribers.add(onMessage);
  if (onStatus) entry.statusSubscribers.add(onStatus);

  return () => {
    const current = registry.get(url);
    if (!current) return;
    current.subscribers.delete(onMessage);
    if (onStatus) current.statusSubscribers.delete(onStatus);
    if (current.subscribers.size === 0) {
      current.es.close();
      registry.delete(url);
    }
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/ui && pnpm exec vitest run src/lib/hooks/eventSourceRegistry.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/lib/hooks/eventSourceRegistry.ts projects/ui/src/lib/hooks/eventSourceRegistry.test.ts
git commit -m "feat: expose reconnect status on shared EventSource registry"
```

---

## Final verification (before PR)

- [ ] **Full UI test suite green:** `cd projects/ui && pnpm test`
- [ ] **Lint + typecheck green:** `cd projects/ui && pnpm lint`
- [ ] **Manual smoke (live API):** run `make dev` (or the 3-terminal hybrid live-API mode), open a work-item thread, send a message, and confirm: (a) the reply appears essentially as soon as the typing indicator disappears — no ~2s idle gap; (b) starting a run flips the status badge to a terminal state immediately when the run finishes; (c) with both the sidebar chat and the Detail Thread tab open for the same item, the browser Network tab shows **one** `activity/stream` connection, not two.
- [ ] **Open the PR:** `git push -u origin fix/realtime-ui-responsiveness && gh pr create` with a focused title (`fix: realtime UI responsiveness (typing race, run status, SSE socket dedupe)`), a summary linking back to PR #73 (the async-SSE backend fix this completes), and the test plan above.

---

## Roadmap: follow-up plans (out of scope for this PR)

This PR closes the **client-side** latency/jitter now that the async-SSE backend (PR #73) removed the event-loop freeze. The remaining structural latency floors are **separate plans**, each its own PR, in priority order:

- **P1.1 — Bus push-wakeup.** Publish currently only becomes visible on the next Celery Beat tick (`celery_app.py`, `schedule=1.0`) → ~0.5s avg pickup floor. Add Postgres `LISTEN/NOTIFY` (or Redis pub/sub) on publish to drain immediately; keep Beat as a slow safety-net sweep.
- **P1.2 — Split interactive from batch.** `worker_concurrency=1` serializes chat behind long run turns (the unbounded tail). Put chat on its own Celery queue/worker; if run concurrency >1 is wanted, add `pg_try_advisory_xact_lock` to `claim_next` to keep the one-in-flight invariant race-free.
- **P1.3 — Stream chat replies.** Bridge `agent_events` into the thread so replies render block-by-block instead of poll-appearing, and multiplex run+chat over one connection per page (builds on this PR's shared registry).
- **P2.1 — Provider streaming parity.** Intra-stage `agent_events` only fire on the `claude_cli` provider; make the `claude`/`litellm` adapters emit them, and flush the `run_events` LOG stream incrementally instead of at stage-end.
- **P2.2 — Board/data-layer cleanup.** Remove the dead `useBoard` layer, align List/Board freshness, and add a mock `/activity/stream` handler so the activity SSE path is exercised in dev/tests.
