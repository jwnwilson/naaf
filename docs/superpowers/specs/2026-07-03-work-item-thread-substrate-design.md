# Work-Item Thread as the Conversation Substrate (Design)

**Date:** 2026-07-03
**Status:** Approved (design) — ready for implementation plan
**Phase:** A6 messaging (extends the merged messaging foundation) + pulls forward agent↔agent dispatch

## Summary

Make the **work item** — not the run — the unit a conversation is scoped to, and make that
conversation the **single substrate** through which humans and agents (and agents and each
other) communicate. One `Thread` per work item is the source of truth; the sidebar chat, the
inbox conversation pane, and a new Detail **Thread** tab all render the *same* thread. Runs
become *spans of activity within* a thread rather than owners of it.

Agent↔agent coordination runs **on top of the existing durable bus**: a message posted to a
thread is parsed for `@role` mentions, and each mention fans out onto that role's work-queue so
the mentioned agent is woken to process it and post its reply back into the same thread. This
directly realizes `docs/TODO.md`:

> Brainstorm queue + pub sub pattern implementation for each agent so they can discover and
> dispatch messages to each other.
> Make chat and inbox chat the same.

It also matches the updated design docs (`docs/design/README.md` changelog + `NAAF Hi-Fi.dc.html`
frames **D3** "Thread tab — scoped conversation for NAAF-42" and **G** "Inbox — thread-style
bubbles matching D3").

## Decisions (locked during brainstorming)

1. **Scope** — full design *including* agent-produced chat.
2. **Depth** — build real agent→agent dispatch now (not just a stub).
3. **Thread↔bus model** — **the thread IS the substrate**; `@mention` = dispatch. The bus is the
   delivery mechanism *under* one conversation model (not a separate world the thread mirrors).
4. **Agent identity** — **role-addressed, one instance per role** (`@lead`, `@backend`,
   `@frontend`, `@qa`, `@architect`, `@devops`). The `author_role` + optional instance-suffix
   scheme is designed so multi-instance (`build-01`/`build-02`) drops in during phase B.

## Current state (on `main`)

- **Messaging foundation** (`docs/superpowers/plans/2026-07-02-messaging-foundation.md`):
  a `Message` store + a run-thread API where **`thread == run`**. `domain/messaging/thread.py`
  derives a `ThreadView` from a `Run`; `domain/messaging/message.py` is
  `{thread_id (==run_id), role (user|agent|lead_agent), content, agent_id}`.
  `interactors/api/routes/threads.py`: `GET /threads` (lists runs), `GET /threads/{id}/messages`,
  `POST /threads/{id}/messages` (**user→persist only; no bus publish yet**).
  `MessageRow` (migration `0007`) — `thread_id`, `role`, `agent_id`, `content`.
- **Durable bus** (`domain/runs/messages.py`, `adapters/database/repositories.py::BusMessageRepository`):
  `AgentMessage {run_id, recipient, role, type, payload, status}`; `recipient_key(run_id, role)`
  = `run:{run_id}:{role}`; role-based `claim_next(roles)` with a **one-in-flight-per-recipient**
  invariant. `interactors/worker/handlers.py::dispatch` routes a claimed message to
  `_HANDLERS[role]` (`handle_lead`/`handle_engineer`/`handle_qa`); `_handoff`/`_report` publish
  onto role queues; gates set `run.pending_gate` and are resolved via `POST /runs/{id}/gate` →
  a `GATE_RESOLVED` bus message.
- **Run observability** — `RunEvent` + SSE (`GET /runs/{id}/events/stream`) is a *separate*,
  low-level event stream (stage started/passed/failed, logs, gate requested). It stays.
- **Frontend** — `app/ChatPanel.tsx` (sidebar, picks `threads[0]`), `modules/inbox/*`
  (`InboxScreen`, `InboxList`, `NotificationItem`, `ConversationPane`), `modules/detail/*`
  (`DetailScreen`, `TabBar` with a `Subagents` tab). Hooks `useThreads`, `useThreadMessages`,
  `useSendMessage`; MSW mock layer + `schema.d.ts`.

**The gap:** a thread is bound to a *run*, so it can't be the work-item-level conversation the
design shows; agents don't post chat; there is no `@mention` dispatch; the inbox/sidebar/detail
render three different things.

## Target architecture

### 1. Thread = work item (no separate table)

Thread identity is the **work-item id** (`thread_id == work_item_id`), 1:1. There is **no
`Thread` table** — thread metadata (title, status, breadcrumb), **participants** (distinct
message senders ∪ assigned roles), and the **files-written** rail all *derive* from the work
item and its messages (YAGNI). `domain/messaging/thread.py` stops deriving from `Run` and
instead assembles a `ThreadView` from a work item + a message summary.

### 2. Message model (reshaped)

`domain/messaging/message.py` becomes:

| Field | Purpose |
|-------|---------|
| `thread_id` | **= work_item_id** (was run_id) |
| `author_kind` | `user` \| `agent` |
| `author_role` | `lead`/`backend`/`frontend`/`qa`/`architect`/`devops` — `None` for a user |
| `model_alias` | optional — renders the `claude-opus-4` badge |
| `kind` | `text` \| `file_write` \| `question` \| `event` |
| `content` | body text |
| `mentions` | `list[str]` roles parsed from `@role` tokens |
| `payload` | kind-specific — `file_write`: `{path, lines}`; `question`: `{options: [{id,label}], resolved_option}` |
| `run_id` | optional back-reference (which run produced it) for grouping/rails |

The mockup's rich cards (file-write card, question-with-Option-A/B) are message **kinds** with
structured payloads — no new entities.

### 3. Dispatch: `@mention` → bus → worker → reply

The existing bus is the delivery layer under the thread:

1. A message is posted to a thread — by a human (API) or an agent (runtime). The domain parses
   `@role` mentions. A human post with **no** mention defaults to `@lead`.
2. For each mentioned role, publish a bus `AgentMessage` with a **new `type=CHAT`** onto that
   role's queue. The recipient scheme moves to **work-item + role**:
   `recipient_key(work_item_id, role)` = `wi:{work_item_id}:{role}` (the run-scoped
   `run:{run_id}:{role}` form stays for the run pipeline; both coexist, keyed by prefix).
3. A role worker claims it (role-based `claim_next`, unchanged), loads recent thread context,
   runs the role-agent through the existing `LlmAgentRuntime`/`FakeAgentRuntime` with a
   "respond in this thread" task, and posts the agent's output back as a new `Message`
   (`text`/`file_write`/`question`). A reply that mentions others fans out again.
4. **Runs narrate into the thread**: each stage handoff/report/gate *additionally* emits a
   human-readable `Message` (Lead assigns → engineer `file_write` card → gate → `question`), so
   run activity appears in the same conversation. `RunEvent`/SSE stays as the low-level stream;
   thread messages are the human narrative.

A new worker handler (`handle_chat`) processes `type=CHAT` messages; the existing
`handle_lead`/`handle_engineer`/`handle_qa` (run pipeline) are untouched.

### 4. Gates become questions

A `question` message carries options; a human answering (button or reply) delivers the decision
to the waiting agent through the **same path** as today's `GATE_RESOLVED`. Existing plan/merge
gates render as question messages so the inbox and thread show them uniformly. The run's
`pending_gate` stays the run-state anchor; the question message is its thread projection and
resolution entry point.

## API surface (`/threads`, work-item-scoped, envelope + owner-scoped)

| Endpoint | Purpose |
|----------|---------|
| `GET /threads` | Threads for inbox + sidebar: `{id=workItemId, title, status, breadcrumb, lastMessage, attention, participants[]}`. `attention` ∈ `action_needed`/`review`/`info`/`resolved`, derived from unresolved `question` messages + run state. |
| `GET /threads/{workItemId}` | Thread detail: metadata, participants, filesWritten (derived). |
| `GET /threads/{workItemId}/messages` | Messages with `kind`/`payload`/`mentions`/`model`. |
| `POST /threads/{workItemId}/messages` | Post a user message → persist → parse mentions → fan out to bus. Returns created message. |
| `POST /threads/{workItemId}/messages/{msgId}/answer` | Answer a `question` message (`{option}`) → posts the answer + delivers the decision to the waiting agent. `POST /runs/{id}/gate` keeps working, routed through the same resolution path. |

`thread_id` is validated against a work item the caller owns (404 otherwise), replacing today's
"read the run" check.

## Frontend — one `<Thread>` component

A single kind-aware conversation component renders text bubbles, `file_write` cards, `question`
messages with option buttons, and `event` dividers, with **optional** participants/files rails.
Three consumers:

- **Detail "Thread" tab** — rename `Subagents` → `Thread` (`TabBar.tsx`, `DetailScreen.tsx`);
  full component **with** the right rail (Participants / Thread info / Files written).
- **Inbox conversation pane** — same component **+** the task-link banner ("Thread scoped to
  NAAF-42 · title · breadcrumb ↗") and the inbox header/Mark-resolved; `ConversationPane.tsx`
  becomes a thin wrapper.
- **Sidebar `ChatPanel`** — compact variant (no rail) showing the thread for the
  **currently-open work item** (contextual), falling back to a recent thread when none is open.
  This is what makes "chat and inbox chat the same."

Inbox list rows become work-item threads with attention state (`NotificationItem` → thread-row).
New hooks `useThread`, `useThreadMessages`, `useSendMessage`, `useAnswerQuestion`, keyed by
`workItemId`; MSW mock layer, fixtures, and `schema.d.ts` update to the new contract.
Notifications stay the **separate** alert channel (notifications only signal; the thread is the
chat).

## Loop safety (agent↔agent can cycle)

`@mention` fan-out (A→B→A…) is guarded in the **domain** layer:

- **Turn/depth budget per thread** — a max auto-reply chain length; on exceed, the thread pauses
  and requires a human message to continue.
- **Addressing constraint** — agents may only mention roles present on the team.
- **Dedupe** — the existing one-in-flight-per-recipient invariant + not re-dispatching an
  identical pending chat message.
- **Cost/token budget** — extend per-run token tracking to a per-thread ceiling; hitting it
  pauses dispatch (ties into A5d budget work later).

## Testing (TDD)

- **Domain** — `@mention` parsing; message kinds; question resolution; loop-guard/turn-budget;
  default-to-lead routing.
- **Adapters** — `MessageRepository` (work-item + owner scoped); work-item+role recipient scheme
  (`wi:{id}:{role}`) alongside the run scheme.
- **API** — thread list/detail/messages/post/answer envelopes; owner-scoping 404s.
- **Worker** — `handle_chat` (mention → role-agent runs → reply posted back); run-stage → thread
  message emission; gate → question round-trip.
- **FE** — `<Thread>` rendering per kind; inbox banner + attention rows; sidebar contextual
  thread; send/answer flows via MSW; `App.integration` updates.

Keep the 80% coverage gate and `make lint` green.

## Migration

The DB migration **repurposes** `messages.thread_id` from run_id → work_item_id and adds columns
(`author_kind`, `author_role`, `model_alias`, `kind`, `mentions`, `payload`, `run_id`). Because
the message store is new (`0007`) and only user posts exist today, this is treated as a
**reshape with no real data to preserve** (drop/recreate semantics), not a careful backfill.

## Shippable phasing (each a mergeable PR)

1. **Work-item thread model + API + FE unification** — reshape `Message` (migration),
   work-item-scoped `/threads`, the shared `<Thread>` component wired into the Detail tab +
   inbox + sidebar. Humans can post; agents don't reply yet. *Delivers the whole visible
   redesign.*
2. **Runs narrate into the thread** — the pipeline emits `text`/`file_write`/`question`
   messages; run gates render + resolve as questions in the thread/inbox.
3. **`@mention` dispatch** — chat message → bus (`wi:{id}:{role}`) → role-agent replies into the
   thread, with the loop guards. *Delivers autonomous agent↔agent chat.*

## Out of scope (deferred)

- **Multi-instance agents** (`build-01`/`build-02` in parallel) — phase B; the `author_role`
  scheme is designed to extend to instance ids.
- **Attachments / file upload** in the composer (the `+ attach` affordance) — later.
- **Real per-model pricing** for the token/cost meter — A5d.
- **Notification system rework** — stays the separate alert channel.
