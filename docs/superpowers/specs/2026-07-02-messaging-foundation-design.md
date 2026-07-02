# Messaging Foundation — Run-Threads & User→Agent Chat (Design)

**Date:** 2026-07-02
**Status:** Approved (design) — ready for implementation plan
**Phase:** A6 (messaging layer), first slice

## Summary

Build the first slice of the A6 messaging layer: a **conversational message store**,
a **read/send API** shaped exactly like the UI's existing (mock) `Thread`/`Message`
contract, and the **UI wiring** that makes the inbox and the sidebar chat panel two
views of the same live data. A **thread is a run** (one team conversation per run);
messages carry a role (`user` / `agent` / `lead_agent`) and free-text content. The
user can post a message into a run-thread; it is **persisted only** (no bus publish
yet — see Non-Goals).

This is deliberately scoped as a foundation. Agents do not yet **produce** chat
messages (that is coupled to the A5 Claude Code runtime, not built) — so in practice
the live chat contains the user's own messages plus any seeded/fake agent messages
until the runtime lands.

## Background & motivation

The intended architecture (recorded, user-stated):

- **Notifications only alert** the user that there are new messages — a lightweight
  signal. They are **not** the inbox content.
- **The inbox is a full chat view**: all messages between all agents, plus the ability
  to chat to any agent.
- **The sidebar chat window is a smaller version of the inbox** — same API and logic,
  compact UI.

Today none of that backend exists:

- The pub/sub **bus** (`bus_messages`) carries **machine control messages**
  (`type: START / RUN_STAGE / STAGE_REPORT / GATE_RESOLVED`, a `payload` dict, keyed
  `run:<id>:<role>`). No sender, no free-text content, no thread — **not chat.**
- There is **no** message / thread / conversation domain, API, or persistence.
- The UI sidebar `ChatPanel` and the inbox conversation pane are **fully mocked**
  against `/threads` + `/threads/{id}/messages`, returning a `Message`
  (`role: user/agent/lead_agent`, `content`, `conversationId`, `createdAt`) and a
  `Thread` (`id, agentId, workItemId?, createdAt`) — shapes that exist only in the mock.

This slice creates the real backend for those shapes and wires the two UI surfaces to it.

## Goals

1. A conversational `Message` domain model + persistence, owner-scoped, separate from
   the orchestration bus.
2. `GET /threads` — list a user's run-threads in the `Thread` shape.
3. `GET /threads/{id}/messages` — list a run-thread's messages in the `Message` shape.
4. `POST /threads/{id}/messages` — persist a user message and return it.
5. Wire the **inbox** (left list → `/threads`; conversation pane → messages + a live
   compose box) and the **sidebar `ChatPanel`** (live messages + live send) to the same
   API via one shared set of hooks.
6. Retire the `/inbox` / `InboxItem` mock; keep notifications as the separate alert channel.

## Non-Goals (explicitly deferred)

- **Agents producing chat messages** (#3 in the roadmap breakdown) — coupled to the A5
  Claude Code runtime. Deferred.
- **Chat → bus bridge on send.** Because no agent consumes chat yet, `POST` **persists
  only**; publishing a bus `AgentMessage` on send lands with the runtime.
- **New-message → notification alerts.** Notifications remain gate/run-finished alerts;
  new-message alerts arrive once agents emit chat.
- **Attachments.** The mock `Message.attachments` field is not populated; nothing
  produces attachments yet.
- **Threads not tied to a run.** You chat *into a run*; there is no standalone
  agent DM outside a run.

## Architecture

Hexagonal, per `docs/architecture.md`. A conversational message is a new concept kept
**separate from `bus_messages`** — the bus stays orchestration transport; this is
human-readable chat.

### Data model

**Thread = run, 1:1 — no new thread table.** `GET /threads` projects owner-scoped
**runs** into the `Thread` shape. A run already carries identity, owner, and work-item;
a parallel Thread entity would only mirror it (KISS/YAGNI).

| `ThreadOut` field | Source on the run |
|---|---|
| `id` | `run.id` |
| `agentId` | the run's lead role (see "Thread projection" below) |
| `workItemId` | `run.work_item_id` |
| `createdAt` | `run.created_at` (ISO-8601 string) |

**New `messages` table** + `Message` domain model.

`Message` (domain, `domain/messaging/message.py`):

```python
class MessageRole(StrEnum):
    USER = "user"
    AGENT = "agent"
    LEAD_AGENT = "lead_agent"

class Message(BaseModel):
    id: str = Field(default_factory=new_id)      # 32-char uuid hex
    owner_id: str
    thread_id: str                                # == run_id
    role: MessageRole
    agent_id: str | None = None
    content: str
    created_at: datetime = Field(default_factory=utcnow)
```

`MessageRow` ORM (`adapters/database/orm.py`), table `messages`:

- `id` PK (String(32)), `owner_id` (String, indexed), `thread_id` (String(32), indexed),
  `role` (String(16)), `agent_id` (String(128), nullable), `content` (Text),
  plus `_Timestamped` (`created_at`, `updated_at`).
- Index on `(owner_id, thread_id)` to serve the per-thread read efficiently.

### Layering

- **domain/** — `Message` model, `MessageRole`, and the pure `run → ThreadOut`
  projection helper. No I/O, no adapter imports.
- **adapters/database/** — `MessageRow`, `MessageRepository` (**all** SQLAlchemy
  `select`/ORM lives here), registration in `repositories.py`/`uow.py`, and an Alembic
  migration creating `messages`.
- **interactors/api/** — `contract.py` (`ThreadOut`, `MessageOut`, `MessageCreate`),
  `routes/threads.py`, wiring in the app factory.

### Ownership & isolation

Every `messages` row carries `owner_id`; the UnitOfWork applies it as a required filter
on every query, exactly like existing rows. A user can only read/post within their own
runs; reading or posting to another owner's run-thread returns 404.

## API contract

All responses use the standard envelope `{success, data, error}` (+ `meta` for
pagination). camelCase field names.

### `GET /threads`

List the caller's run-threads, newest first, paginated (`page_number`, `page_size`).

`ThreadOut`: `{ id, agentId, workItemId, createdAt }` — as projected above.

### `GET /threads/{id}/messages`

List a run-thread's messages, **oldest-first** (chat order), paginated.

`MessageOut`: `{ id, conversationId, role, agentId, content, createdAt }` where
`conversationId == thread_id == run_id`.

- `404` if the run/thread is not the caller's or does not exist.

### `POST /threads/{id}/messages`

Persist a **user** message in the run-thread and return it.

- Body `MessageCreate`: `{ content: str (non-empty), agentId?: str | null }`.
- Server sets `role = user`, `owner_id = caller`, `thread_id = id`, `id`, `created_at`.
- Returns `MessageOut` for the created message (envelope `data`).
- `404` if the run/thread is not the caller's or does not exist.
- `422` on empty/whitespace-only `content` (schema validation at the boundary).
- **Persist-only** — no bus publish (see Non-Goals).

## Thread projection (run → ThreadOut)

`agentId` is the run's **lead role**. Runs drive stages through roles; the lead role is
the stable identifier for "who you're talking to" in a run's team conversation. The
implementation plan will read the concrete run field/constant that names the lead role
(e.g. a `lead`/`team_lead` role constant already used by the run pipeline) and use it
verbatim; it must not invent a new role name. If a run has no natural lead role value,
`agentId` falls back to a single documented constant defined in the plan.

## UI wiring

### Shared hooks (single source, no drift)

`projects/ui/src/lib/api/hooks/`:

- `useThreads()` — already exists (`GET /threads`, `Thread[]`). Keep; move it (and the
  message hooks) onto the enveloped `apiList` client so raw-array vs enveloped handling
  is consistent (the current mock mixes both).
- `useThreadMessages(threadId)` — one shared hook for the thread's messages
  (`GET /threads/{id}/messages`). Replaces the ad-hoc copies inside `ChatPanel`
  (`useThreadMessages`) and inbox (`useInboxConversation`).
- `useSendMessage(threadId)` — `POST /threads/{id}/messages`; optimistic append then
  React Query invalidate of the thread's messages key.

Inbox and sidebar consume the same three hooks — the sidebar is literally a compact
render of the same data.

### Inbox

- Left list: `useInbox` / `/inbox` → `useThreads` / `/threads`. Each row is a run-thread.
  `InboxList` / `NotificationItem` re-work to render a `Thread` (label from `agentId` /
  `workItemId`), not an `InboxItem`.
- `InboxScreen`: selection keyed by thread id; empty state "No conversations".
- `ConversationPane`: takes a `threadId` (not an `InboxItem`); reads
  `useThreadMessages`; gains a **compose box** wired to `useSendMessage`.

### Sidebar `ChatPanel`

- Replace the local `useThreadMessages` with the shared hook.
- `ChatInput` becomes live: controlled input → `useSendMessage` on submit (was inert).

### Mocks / retirement

- MSW `/threads` + `/threads/{id}/messages` (GET/POST) handlers move to `liveHandlers`
  behind `VITE_LIVE_API`; the default fully-mocked demo keeps working.
- Remove the `/inbox` mock surface: `InboxItem` schema, `listInbox` / `getInboxItem` /
  `markInboxItemRead` / `markAllInboxRead` operations, `/inbox*` handlers, and the
  `db.inboxItems` fixture usage — nothing renders `InboxItem` after this change.
- Regenerate `schema.d.ts` from the backend OpenAPI so `Thread` / `Message` reflect the
  live contract.

### Notifications

No backend change. The UI continues to treat `/notifications` as the alert channel
(badge/bell). The inbox is no longer sourced from notifications or `/inbox`.

## Error handling

- Boundary validation: empty/whitespace `content` → `422` (Pydantic).
- Owner isolation / missing thread → `404` (uniform, no leak of existence).
- All errors returned in the standard envelope (`success: false`, `error` populated).
- UI: send failure rolls back the optimistic message and surfaces an inline error;
  message-list load error shows a retryable state.

## Testing

TDD throughout; ≥80% coverage gate; AAA structure; descriptive names.

**Backend (pytest, SQLite in-memory):**

- `MessageRepository`: create + list-by-thread ordering (oldest-first), pagination,
  owner-scoped isolation (another owner sees nothing / 404 path).
- Thread projection: `run → ThreadOut` field mapping, including the lead-role `agentId`
  and the no-lead fallback.
- Routes: `GET /threads` (envelope, pagination, owner isolation);
  `GET /threads/{id}/messages` (order, envelope, 404 for foreign/missing);
  `POST` (persists `role=user`, returns `MessageOut`, 404 foreign/missing,
  422 empty content, and **does not** publish to the bus).

**Frontend (vitest + MSW):**

- Shared hooks against mocked fetch: list threads, list messages, send (optimistic add
  + invalidate; rollback on error).
- `ConversationPane`: renders messages, compose box sends, optimistic update.
- `ChatPanel`: renders messages, live `ChatInput` send.
- Inbox list renders run-threads from `/threads`; empty state.
- MSW live-vs-mock flag: `/threads` handlers honour `VITE_LIVE_API`.

## Rollout / sequencing

1. Backend domain + ORM + repository + migration (persistence).
2. Backend contract + routes + wiring (API).
3. `schema.d.ts` regeneration + shared UI hooks.
4. Inbox re-work (list from threads, conversation pane + compose).
5. Sidebar `ChatPanel` live send.
6. Mock retirement (`/inbox`, `InboxItem`) + MSW live handlers.

Each step is independently testable and leaves the app working (default-mock demo intact
throughout).

## Open questions

None blocking. The lead-role field name for `agentId` projection is resolved during
planning by reading the run pipeline's existing role constant (see "Thread projection").
