# Chat auto-scroll to bottom — design

> Status: approved for planning · 2026-07-05
> Feature: the chat thread should show the newest message by default and follow new
> messages/streaming activity, without yanking a user who has scrolled up.

## Goal

The shared `<Thread>` message list currently opens scrolled to the **top** (oldest messages); new
agent replies and streaming activity append below the fold, so a user has to manually scroll down to
see the latest. Make the chat land at the bottom on open and follow new content — the standard chat
experience.

Because the Detail Thread tab, the inbox pane, and the sidebar chat all render the same
`components/thread/Thread.tsx`, this single change fixes every chat surface.

## Decisions (from brainstorming)

- **Land at bottom on open / thread switch**, then **follow new messages + streaming activity — but
  only while the user is near the bottom.** If they've scrolled up to read history, don't force them
  down.
- **Near-bottom threshold:** 50px.
- **Instant scroll** (`scrollTop = scrollHeight`), not smooth — avoids animation jank at the
  poll/stream cadence.

## Component

`projects/ui/src/components/thread/Thread.tsx` (the only file with behavior change):

- `scrollRef: RefObject<HTMLDivElement>` on the existing scroll container (the
  `div.flex-1.overflow-y-auto` at line 46).
- `atBottomRef: RefObject<boolean>` (a ref, **not** state — updating it must not re-render), default
  `true`. An `onScroll` handler on the container recomputes it via the pure helper.
- **Follow effect** — `useEffect` keyed on the content that grows: `messages.length`,
  `activity.textBlocks.length`, `activity.toolCalls.length`, `activity.isWorking`. When it fires, if
  `atBottomRef.current` is true, set `scrollRef.current.scrollTop = scrollRef.current.scrollHeight`.
  This covers both the initial load (messages 0 → N) and every subsequent new message/activity chunk.
- **Thread-switch effect** — `useEffect` keyed on `workItemId`: reset `atBottomRef.current = true` so
  switching threads always lands at the bottom (its messages then arrive and the follow effect
  scrolls).

## Pure helper — `components/thread/autoscroll.ts`

```
isNearBottom(el: { scrollTop: number; scrollHeight: number; clientHeight: number }, threshold = 50): boolean
  = el.scrollHeight - el.scrollTop - el.clientHeight <= threshold
```

Pure, dependency-free, unit-testable. The `onScroll` handler calls it with the container element to
update `atBottomRef`.

## Testing

- **Unit** (`autoscroll.test.ts`): `isNearBottom` returns true at the bottom (`scrollTop` such that
  the gap ≤ threshold), false when scrolled up (gap > threshold), true for a short/non-overflowing
  list (`scrollHeight <= clientHeight`), and respects a custom threshold.
- **Component** (`Thread.test.tsx`, existing): stays green — the render is unchanged. Note: jsdom does
  not implement layout, so `scrollHeight`/`scrollTop`/`clientHeight` are all 0 and actual scroll
  *position* cannot be asserted in a jsdom test; the pure helper carries the logic coverage. Manual
  verification of the scroll behavior happens in the running app.
- **Gates:** UI `pnpm test` + `pnpm lint` + `pnpm build`. (No backend change — `make coverage`/`make
  lint` on the server are unaffected.)

## Out of scope

- Smooth-scroll animation, a "jump to latest" button / new-message pill, or unread markers — not
  requested; instant follow is sufficient.
- Any change to `useThreadMessages` polling or the activity stream.
