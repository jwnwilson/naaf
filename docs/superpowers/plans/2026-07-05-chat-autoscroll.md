# Chat Auto-Scroll to Bottom Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The shared chat `<Thread>` lands at the newest message on open and follows new messages/streaming activity, without yanking a user who has scrolled up.

**Architecture:** A pure `isNearBottom` helper carries the near-bottom logic; `Thread.tsx` adds a scroll-container ref + an `atBottomRef` updated on scroll, and two effects (reset-on-thread-switch, follow-on-new-content) that set `scrollTop = scrollHeight` only when the user is near the bottom. One shared component → fixes the Detail tab, inbox, and sidebar chat at once.

**Tech Stack:** React + TypeScript + Vitest.

## Global Constraints

- Only `projects/ui/src/components/thread/Thread.tsx` changes behavior; the new pure helper is `projects/ui/src/components/thread/autoscroll.ts`. No backend change.
- Near-bottom threshold: **50px** (default arg). `isNearBottom(el, threshold=50) = el.scrollHeight - el.scrollTop - el.clientHeight <= threshold`.
- Follow only when near bottom; **instant** scroll (`scrollTop = scrollHeight`), not smooth.
- `atBottomRef` is a `useRef` (not state) — the scroll handler must not re-render.
- On `workItemId` change, reset `atBottomRef.current = true` so a thread switch always lands at bottom; the reset effect must be declared BEFORE the follow effect (React runs effects in order).
- jsdom has no layout, so scroll *position* isn't asserted in component tests — the pure helper carries logic coverage; the existing `Thread.test.tsx` must stay green.
- TDD; UI gates `pnpm test` + `pnpm lint` + `pnpm build`. Commit format `<type>: <description>`.

## File Structure
- Create: `projects/ui/src/components/thread/autoscroll.ts` — `ScrollMetrics` type + `isNearBottom`.
- Create: `projects/ui/src/components/thread/autoscroll.test.ts` — unit tests.
- Modify: `projects/ui/src/components/thread/Thread.tsx` — ref + handler + two effects.

---

### Task 1: `isNearBottom` pure helper

**Files:**
- Create: `projects/ui/src/components/thread/autoscroll.ts`
- Create: `projects/ui/src/components/thread/autoscroll.test.ts`

**Interfaces:**
- Produces: `ScrollMetrics = { scrollTop: number; scrollHeight: number; clientHeight: number }`; `isNearBottom(el: ScrollMetrics, threshold?: number): boolean` (default threshold 50).

- [ ] **Step 1: Write the failing test**

Create `projects/ui/src/components/thread/autoscroll.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { isNearBottom } from "./autoscroll";

describe("isNearBottom", () => {
  it("is true when scrolled to the very bottom (gap 0)", () => {
    expect(isNearBottom({ scrollTop: 950, scrollHeight: 1000, clientHeight: 50 })).toBe(true);
  });

  it("is true within the default 50px threshold (gap 40)", () => {
    expect(isNearBottom({ scrollTop: 910, scrollHeight: 1000, clientHeight: 50 })).toBe(true);
  });

  it("is false when scrolled up beyond the threshold (gap 850)", () => {
    expect(isNearBottom({ scrollTop: 100, scrollHeight: 1000, clientHeight: 50 })).toBe(false);
  });

  it("is true for a short, non-overflowing list (negative gap)", () => {
    expect(isNearBottom({ scrollTop: 0, scrollHeight: 40, clientHeight: 300 })).toBe(true);
  });

  it("respects a custom threshold", () => {
    // gap = 1000 - 800 - 50 = 150
    expect(isNearBottom({ scrollTop: 800, scrollHeight: 1000, clientHeight: 50 }, 200)).toBe(true);
    expect(isNearBottom({ scrollTop: 800, scrollHeight: 1000, clientHeight: 50 })).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm test -- autoscroll`
Expected: FAIL — `isNearBottom` module not found.

- [ ] **Step 3: Write minimal implementation**

Create `projects/ui/src/components/thread/autoscroll.ts`:

```ts
export interface ScrollMetrics {
  scrollTop: number;
  scrollHeight: number;
  clientHeight: number;
}

/** True when the scroll position is within `threshold` px of the bottom (or the
 * content doesn't overflow). Used to decide whether to auto-follow new messages. */
export function isNearBottom(el: ScrollMetrics, threshold = 50): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight <= threshold;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/ui && pnpm test -- autoscroll`
Expected: all 5 assertions PASS.

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/components/thread/autoscroll.ts projects/ui/src/components/thread/autoscroll.test.ts
git commit -m "feat: isNearBottom helper for chat auto-scroll"
```

---

### Task 2: Wire auto-scroll into `Thread.tsx` + ship

**Files:**
- Modify: `projects/ui/src/components/thread/Thread.tsx`

**Interfaces:**
- Consumes: `isNearBottom` (Task 1).

- [ ] **Step 1: Apply the change**

Edit `projects/ui/src/components/thread/Thread.tsx`. Change the React import (line 1) to also import `useEffect`/`useRef`, and import the helper:

```tsx
import { useEffect, useRef, type ReactNode } from "react";
```

Add (after the other imports, near line 8):

```tsx
import { isNearBottom } from "./autoscroll";
```

Inside the `Thread` component body, after `const groups = groupMessagesByDay(messages);`, add the refs, handler, and two effects:

```tsx
  const scrollRef = useRef<HTMLDivElement>(null);
  const atBottomRef = useRef(true);

  const handleScroll = () => {
    const el = scrollRef.current;
    if (el) atBottomRef.current = isNearBottom(el);
  };

  // Switching threads always lands at the bottom. Declared BEFORE the follow
  // effect so atBottomRef is true when it runs on the same workItemId change.
  useEffect(() => {
    atBottomRef.current = true;
  }, [workItemId]);

  // Follow new messages / streaming activity while pinned near the bottom.
  useEffect(() => {
    const el = scrollRef.current;
    if (el && atBottomRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [
    workItemId,
    messages.length,
    activity.textBlocks.length,
    activity.toolCalls.length,
    activity.isWorking,
  ]);
```

Attach the ref + scroll handler to the existing scroll container (the
`<div className="flex-1 overflow-y-auto px-4 py-4">`):

```tsx
          <div
            ref={scrollRef}
            onScroll={handleScroll}
            className="flex-1 overflow-y-auto px-4 py-4"
          >
```

Leave everything inside that div (loading text, groups, `ActivityFeedView`), the composer, and the rail unchanged.

- [ ] **Step 2: Run the full UI suite**

Run: `cd projects/ui && pnpm test`
Expected: all pass, including the existing `Thread.test.tsx` (render is unchanged; the effects are inert in jsdom since layout metrics are 0, so `atBottomRef` stays true and `scrollTop = scrollHeight` is a no-op assignment).

- [ ] **Step 3: Lint + build**

Run: `cd projects/ui && pnpm lint && pnpm build`
Expected: 0 errors, clean build. (`useEffect`/`useRef` are used; no unused imports.)

- [ ] **Step 4: Commit**

```bash
git add projects/ui/src/components/thread/Thread.tsx
git commit -m "feat: chat thread auto-scrolls to bottom + follows new messages"
```

- [ ] **Step 5: Push and open the PR**

```bash
git push -u origin feat/chat-autoscroll
gh pr create --title "feat: chat auto-scrolls to the bottom by default" --body "$(cat <<'EOF'
## Summary
- The shared `<Thread>` message list now lands at the newest message on open / thread switch and follows new messages + streaming agent activity — but only while the user is near the bottom (50px), so scrolling up to read history isn't interrupted.
- Fixes all three chat surfaces at once (Detail Thread tab, inbox pane, sidebar chat) since they share `components/thread/Thread.tsx`.
- Logic lives in a pure, unit-tested `isNearBottom` helper; `Thread.tsx` adds a scroll ref + `atBottomRef` + two effects. Instant scroll (no animation jank on the poll/stream cadence).

Design: `docs/superpowers/specs/2026-07-05-chat-autoscroll-design.md` · Plan: `docs/superpowers/plans/2026-07-05-chat-autoscroll.md`

## Test plan
- [x] `isNearBottom` unit tests (at-bottom, within/beyond threshold, non-overflowing, custom threshold)
- [x] `cd projects/ui && pnpm test` green (existing Thread.test.tsx unaffected) · `pnpm lint` + `pnpm build` clean
- [ ] Manual (`make dev`): open a work-item thread with history → lands at newest; send a message / run an agent → follows new replies + streaming activity; scroll up → stays put (not yanked down); switch threads → lands at bottom

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review

**1. Spec coverage:** land-at-bottom-on-open + follow-when-near-bottom + reset-on-thread-switch → Task 2 effects. 50px threshold + instant scroll + `isNearBottom` formula → Task 1 helper. Shared-component (all 3 surfaces) → Task 2 edits the one shared file. jsdom-can't-assert-position → noted; existing Thread.test.tsx kept green. Unit tests for the helper → Task 1. ✓

**2. Placeholder scan:** No TBD/TODO/vague steps — both tasks contain complete code.

**3. Type consistency:** `ScrollMetrics`/`isNearBottom(el, threshold=50)` defined in Task 1, consumed in Task 2's `handleScroll` (passes the DOM element, which structurally satisfies `ScrollMetrics`). `scrollRef`/`atBottomRef`/`handleScroll` names consistent within Task 2. Effect dep arrays reference real values (`messages.length`, `activity.textBlocks.length`, `activity.toolCalls.length`, `activity.isWorking`, `workItemId`) that exist in the current `Thread.tsx`.
