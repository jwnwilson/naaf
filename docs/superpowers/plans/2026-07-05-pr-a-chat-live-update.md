# PR-A: Chat live-update (poll thread messages) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agent replies appear in an open chat thread without a manual refresh.

**Architecture:** Root cause — the chat `Thread` shows an agent reply only via the live activity SSE (`ActivityFeedView`), which returns `null` the instant the agent finishes (`isWorking` false), while the persisted `Message` list (`useThreadMessages`) has no polling and is invalidated only once, right after the user's POST. Server-side agent writes never invalidate client queries (same reason `useBoard`/`useDashboard`/`useAgents` poll). Fix: give `useThreadMessages` a `refetchInterval` — faster while an agent is working, slower when idle — mirroring the `useBoard` pattern. This is race-free vs. the worker's commit timing (a terminal-event-triggered invalidate would race the message commit).

**Tech Stack:** React + TanStack Query + Vitest.

## Global Constraints

- Follow the existing polling pattern in `useBoard.ts` (`BOARD_POLL_MS`, `refetchInterval: pollMs`, `refetchIntervalInBackground` left default so polling pauses when the tab is hidden).
- TDD: failing test first; AAA; descriptive names.
- Explicit prop/param types; no `React.FC`; immutable patterns.
- Gates: frontend `pnpm vitest run` + `pnpm tsc --noEmit` + `pnpm lint` green before PR.
- Do NOT hand-edit `schema.d.ts`; no backend changes in this PR.

---

### Task 1: Poll thread messages while the thread is open

**Files:**
- Modify: `projects/ui/src/lib/api/hooks/useThreadMessages.ts`
- Modify: `projects/ui/src/components/thread/Thread.tsx:35,39`
- Test: `projects/ui/src/lib/api/hooks/useThreadMessages.test.tsx` (create)

**Interfaces:**
- Produces: `useThreadMessages(workItemId?: string, active?: boolean)` — polls at `THREAD_ACTIVE_POLL_MS` when `active`, else `THREAD_IDLE_POLL_MS`. Pure helper `threadMessagesPollMs(active: boolean): number`.
- Consumes: `Thread` passes `activity.isWorking` (from `useAgentActivity`, already computed at `Thread.tsx:39`) as `active`.

- [ ] **Step 1: Write the failing test**

Create `projects/ui/src/lib/api/hooks/useThreadMessages.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { threadMessagesPollMs, THREAD_ACTIVE_POLL_MS, THREAD_IDLE_POLL_MS } from "./useThreadMessages";

describe("threadMessagesPollMs", () => {
  it("polls faster while an agent is working", () => {
    expect(threadMessagesPollMs(true)).toBe(THREAD_ACTIVE_POLL_MS);
  });

  it("polls slower when the thread is idle", () => {
    expect(threadMessagesPollMs(false)).toBe(THREAD_IDLE_POLL_MS);
  });

  it("active interval is faster than idle", () => {
    expect(THREAD_ACTIVE_POLL_MS).toBeLessThan(THREAD_IDLE_POLL_MS);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm vitest run src/lib/api/hooks/useThreadMessages.test.tsx`
Expected: FAIL — `threadMessagesPollMs`/constants are not exported.

- [ ] **Step 3: Write minimal implementation**

Replace `projects/ui/src/lib/api/hooks/useThreadMessages.ts` with:

```ts
import { useQuery } from "@tanstack/react-query";
import { apiList } from "../client";
import { queryKeys } from "../queryKeys";
import type { components } from "../schema";

export type Message = components["schemas"]["Message"];

// Agents write messages into a thread server-side, which never invalidates
// client queries. Poll while the thread is open so replies appear live —
// faster while an agent is actively working, slower when idle. Paused
// automatically when the tab is hidden (refetchIntervalInBackground default).
export const THREAD_ACTIVE_POLL_MS = 1500;
export const THREAD_IDLE_POLL_MS = 5000;

export function threadMessagesPollMs(active: boolean): number {
  return active ? THREAD_ACTIVE_POLL_MS : THREAD_IDLE_POLL_MS;
}

export function useThreadMessages(workItemId?: string, active = false) {
  return useQuery({
    queryKey: queryKeys.threadMessages(workItemId),
    queryFn: () => apiList<Message>(`/threads/${workItemId!}/messages`),
    enabled: Boolean(workItemId),
    select: (page) => page.results,
    refetchInterval: threadMessagesPollMs(active),
  });
}
```

- [ ] **Step 4: Wire the active flag in Thread**

In `projects/ui/src/components/thread/Thread.tsx`, the activity is already computed. Reorder so `activity` is available before `useThreadMessages`, and pass `activity.isWorking`:

```tsx
export function Thread({
  workItemId,
  showRail,
  banner,
  composerPlaceholder,
}: ThreadProps) {
  const activity = useAgentActivity({ threadId: workItemId });
  const { data: messages = [], isLoading } = useThreadMessages(workItemId, activity.isWorking);
  const answer = useAnswerQuestion(workItemId);
  const handleAnswer = (msgId: string, option: string) => { answer.mutate({ msgId, option }); };
  const groups = groupMessagesByDay(messages);
  // ...unchanged JSX...
```

(Delete the old `const activity = useAgentActivity(...)` line at its previous position — it now lives above `useThreadMessages`.)

- [ ] **Step 5: Run tests + typecheck to verify they pass**

Run: `cd projects/ui && pnpm vitest run src/lib/api/hooks/useThreadMessages.test.tsx src/components/thread/Thread.test.tsx src/modules/inbox/ConversationPane.test.tsx && pnpm tsc --noEmit`
Expected: PASS, no type errors. (The Thread/ConversationPane tests use jsdom where `EventSource` is skipped and the idle poll interval never fires within a fast test, so they remain green.)

- [ ] **Step 6: Commit**

```bash
git add projects/ui/src/lib/api/hooks/useThreadMessages.ts projects/ui/src/lib/api/hooks/useThreadMessages.test.tsx projects/ui/src/components/thread/Thread.tsx
git commit -m "fix: poll thread messages so agent replies appear without refresh"
```

---

### Task 2: Verify gates and open the PR

**Files:** none.

- [ ] **Step 1: Frontend gates**

Run: `cd projects/ui && pnpm vitest run && pnpm tsc --noEmit && pnpm lint`
Expected: all green (eslint may show the 2 pre-existing warnings in `mockServiceWorker.js` / `queryClient.tsx` — 0 errors).

- [ ] **Step 2: Push and open the PR**

```bash
git push -u origin <branch>
gh pr create --title "fix: chat thread updates live (poll persisted messages)" \
  --body "Root cause + fix per docs/superpowers/plans/2026-07-05-pr-a-chat-live-update.md. The chat Thread showed agent replies only via the live activity SSE, which clears the instant the agent finishes; the persisted message list had no polling, so replies only appeared after a manual refresh. Fix: useThreadMessages polls while the thread is open (faster while an agent works), mirroring useBoard. Test plan: threadMessagesPollMs unit tests; existing Thread/ConversationPane suites green; vitest + tsc + lint."
```

---

## Self-Review
- Root cause (activity feed clears on finish + no message polling) → Task 1 adds polling. ✓
- Race-free: polling doesn't depend on terminal-event vs commit ordering. ✓
- Matches `useBoard` pattern (constants + `refetchInterval`, background-pause default). ✓
- TDD on the pure `threadMessagesPollMs`; wiring is a one-line param. ✓
- No placeholders; no backend/schema changes. ✓
