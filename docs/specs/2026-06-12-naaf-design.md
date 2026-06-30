# naaf — Not Another Agent Framework (Design)

**Date:** 2026-06-12
**Status:** Approved design, pending implementation plan
**Name:** naaf (Not Another Agent Framework)

## 1. Problem & vision

Managing multiple software projects with AI agents today means ad-hoc terminal sessions, no shared memory, no cost visibility, and no controlled execution environment. naaf is a self-hosted platform that lets one user (multi-user-ready) run **virtual dev teams** — role-based agents (team lead, architect, backend/frontend engineers, QA, devops) — against real repositories, driven from a **visual task board** of projects → epics → features → tasks.

Agents work autonomously inside **sandboxed Docker containers** with centrally managed secrets, permissions, skills, tools, MCP servers, and RAG access. Teams produce reviewable PRs, update **persistent memory** as they work, and run on **user-configurable models** with the harness picking sensible defaults per role.

### v1 success criterion

> Create a project pointing at a git repo, chat with a team-lead agent to turn an idea into a ticket on the board, hit **Run**, and watch a sandboxed team (lead + engineer + QA) produce a reviewed PR — with the merge gated on the human.

## 2. Decisions log

| Decision | Choice | Rationale |
|---|---|---|
| Agent engine | **Engine-agnostic `AgentRuntime` port**; default = headless coding agent (Claude Code / Agent SDK); OpenHands & CrewAI-Flows as future adapters | Coding-native agents decisively outperform generic framework agents at repo work; port keeps us unlocked |
| Model access | **LiteLLM gateway**, logical aliases per role, Claude as default models | Model-agnostic per user requirement; budgets/keys/cost tracking built in |
| Orchestration spine | **Local First** | Agents are designed to run locally in docker containers for security and to control the environment agents run in. Each agent will have it's own context, secrets, mcps, tools and can receive messages from other agents which will be queued up and processessed sequentually.

## 3. Architecture

A consistent docker agent pattern with each agent can be sent messages via a pub / sub pattern. These messages will be put on an agent queue which the agent will respond to and then either converse with a user / agent or work on a repository.

## 4. Domain model

Hierarchy: **Project → Epic → Feature → Task** (task = executable unit).

- **Project**: repo (GitHub URL or local path), team assignment, autonomy level, secrets, capability grants, budgets.
- **Work items**: markdown body, **structured acceptance criteria**, status (`To Do → In Progress → In Review → Approved → Done`, plus `Blocked`/`Failed`), activity feed.
- **Run**: one execution of a task through the agent pipeline (`PLAN → PROVISION → IMPLEMENT → VERIFY → PR → LEARN`, see §6). A task can have multiple runs (retries). Each run owns a stage timeline, per-agent logs and cost roll-up, the per-run git token and LiteLLM budget key, and an append-only audit trail; it ends with the sandbox destroyed and tokens revoked. Runs surface on the card panel (run timeline) and on the cross-project **Runs** screen (§5). Budgets and guardrails apply per run (§6, §9).
- **Team**: named, reusable group of **AgentDefinitions**. Each: role (lead/architect/backend/frontend/qa/devops/custom), persona prompt, **model alias**, runtime adapter, capability grants (deny-by-default), memory scope.
- **Refinement chat**: session with the team-lead agent attached to a project/epic; lead drafts epics/features/tasks onto the board live; nothing becomes `Ready` without the user in gated modes.
- **Governance**: `Secret` (encrypted, write-only), `SkillRegistryEntry`, `McpServer`, `ModelAlias`, `AuditEvent` (append-only).

## 5. Board UI

Kanban-first: board is the project home screen. Card click → **slide-over panel**: description, acceptance criteria, run timeline (stage-by-stage), live agent logs (SSE), per-agent cost, ticket-scoped team chat, approve/reject gate buttons. **Toggleable right rail** hosts the persistent team-lead chat (refinement and status flow through conversation while the board updates live).

Other screens: Teams (agents, roles, models, capabilities), Capabilities (skills/MCP/RAG/model registries), Secrets, Runs (cross-project history + costs), Spend dashboard, and a global **attention inbox** for pending gates/escalations. Epics/features render as board filters + a roadmap view.

## 6. Execution flow

1. **PLAN** — lead agent reads ticket + project memory → implementation plan. Architect agent reviews with a **different model** (cross-model review); ≤2 revise loops. ✋ plan gate (`gated_all`).
2. **PROVISION** — sandbox + workspace; mint 1-hour git token; create LiteLLM budget key for the run; assemble capability manifest.
3. **IMPLEMENT** — engineer agent(s) via AgentRuntime in sandbox; progress heartbeats stream to the board; commits to `agent/<task>` branch. Frontend+backend tasks may run parallel agents on split worktrees, lead merges.
5. **PR** — push branch; open PR (remote) or finalize local branch (local). PR body: plan, changes, QA evidence, cost report. ✋ **merge gate — always human unless `full_auto`**; GitHub branch rulesets enforce it server-side regardless (agent App cannot merge to main).
4. **VERIFY** — QA agent in **fresh context** (sees ticket + diff, never the engineer transcript) adversarially tries to falsify "done": runs tests/build/lint, checks acceptance criteria. Fail → back to 3 with QA report; max 3 loops (configurable per project) then ✋ escalate. (Hallucinated completion ≈ 24% of multi-agent failures; never self-certify.)
6. **LEARN** — curator agent (cheap model) distills run into memory diffs; sandbox destroyed, tokens revoked, audit sealed.

Devops role in v1 is thin: deterministic CI does the work; the agent only triages CI failures.

### Guardrails (every run)

- Budgets: max dollars, max turns, max wall-clock per stage → breach pauses + asks the user.
- **No-progress detector** on structured signals (new commits, distinct test results, files touched) — same failing tests N times or zero commits in M active minutes → escalate; never grind.
- **Blocked/infeasible** is a first-class agent action surfacing on the board (the Devin lesson).
- Every stage leaves disk artifacts (`plan.md`, `progress.md`, QA report) so retries/resumes read state from the workspace, not a lossy transcript.

### Supervision & liveness

TBC - polling of lead developer to ensure it is monitoring current tasks and is not stuck.

## 7. Sandbox, secrets & permissions

- **Sandbox hardening** as listed in §3; egress deny-all except the proxy; per-project domain allowlist (git host, package registries, LiteLLM). Blocks metadata IP + RFC1918.
- **Secrets**: encrypted in Postgres, managed in UI, write-only. Agents see placeholders (`__github_token__`); the **credential-injecting proxy** substitutes real values only toward approved hosts, and redacts secrets from response bodies/logs (Infisical Agent Vault pattern). Git auth via credential helper → broker; tokens never in URLs/env/transcripts.
- **GitHub App** identity: per-repo install, `contents` + `pull_requests` write only; 1-hour installation tokens minted per run, revoked after. Rulesets on `main`: require PR + human review; App not on bypass list; optional push ruleset restricting App to `agent/*`.
- **Permissions**: per-role tool allowlists in config, enforced outside the model (PreToolUse-style interceptor in the runtime adapter). Risk tiers: workspace edits/tests = auto; push/install = auto + audited; credentials/out-of-workspace/force-push = blocked or human-approved. All decisions → append-only audit log, viewable per run.

## 8. Memory

Markdown-in-git, three scopes, human-editable (research consensus: files-in-git won for coding agents; vector/graph memory skipped in v1):

| Scope | Location | Contents |
|---|---|---|
| Project | managed repo: `AGENTS.md`/`CLAUDE.md` (≤~120 lines) + `docs/adr/` | conventions, architecture decisions, gotchas — shared by all agents |
| Role | harness memory repo: `roles/<role>.md` | cross-project role heuristics |
| Episodic | per-run `progress.md` in workspace | handoff state for resume/retry |

The **curator agent (Learn stage) is the only writer** to project/role memory: proposes additions *and deletions* as git commits → UI shows reviewable **memory diffs** (auto-applied in `full_auto`, gated otherwise). Write-time curation prevents memory rot.

Code search = grep/AST/LSP tools (no code embeddings — agentic search beat embeddings decisively). Phase B adds optional pgvector RAG over docs/ADRs/run summaries as a grantable capability.

## 9. Capabilities & model management

Four UI registries, enforced at PROVISION via the capability manifest:

- **Skills**: git repo of `SKILL.md` folders (open standard, portable across runtimes); per-role/team grants; UI authoring (edits = commits).
- **MCP servers**: approved-server registry, per-server tool allowlists (`mcp__server__tool`), credentials held by proxy/broker; deny-by-default; read-only sets for QA/review roles.
- **RAG indexes** (phase B): named pgvector indexes, grantable per role as a query tool.
- **Models**: provider credentials, model aliases, **role→alias defaults** (frontier: lead/architect/cross-review; mid: engineers; cheap: triage/QA-checks/curator) with per-agent/team/project overrides. Budgets at run / project-month / global-month. Cost roll-ups on tickets, runs, spend dashboard. LiteLLM version-pinned (post supply-chain incident); single instance is fine for single-user, scale behind an LB sharing Postgres if needed.

## 10. Build phases

**Phase A — the spine** (v1 criterion above): work-item CRUD + board + slide-over; refinement chat; one default team (lead+engineer+QA); pipeline with plan/merge gates; sandbox + egress proxy + GitHub App; Claude Code runtime adapter; LiteLLM static role defaults; project memory + progress files; local & remote profiles.

**Phase B — management plane**: secrets UI; skills/MCP registries; model config + budgets UI; audit log viewer; run inspector (transcripts/costs); autonomy dial UI; memory diff review UI.

**Phase C — full team**: all roles incl. richer architect/devops; custom roles; parallel engineers; role memory curation; second runtime adapter (OpenHands or CrewAI Flows); RAG indexes; chat-rail enhancements; multi-user RBAC.

## 11. Error handling

- Every external system (GitHub, LLM, Docker) behind a port with typed domain errors; no silent swallowing.
- Epics / features / tasks always reach a terminal state (`done`/`failed`/`blocked`); janitor workflow reaps ungraceful deaths.
- User-facing errors are friendly; full context goes to server logs + audit trail.

## 12. Testing

- **Unit**: domain logic — pipeline state machine, budget math, permission rules, capability manifest assembly.
- **Integration**: API endpoints; the run executor / agent message pipeline driven by fakes (scripted agents + a fake message bus, no LLM).
- **Adapter tests with fakes**: `FakeAgentRuntime` scripting agent behavior — full pipeline tests without LLM calls; fake workspace/git fixtures.
- **E2E**: one real ticket against a fixture repo with a stub model through board → run → PR.
- 80% coverage gate in CI (llm_api standard).

## 13. Key research inputs

- MAST failure taxonomy (arXiv:2503.13657): 44% spec/role failures, 32% inter-agent misalignment, 24% verification failures → roles as verified pipeline stages, structured acceptance criteria, fresh-context QA.
- Anthropic: building effective agents / multi-agent research system / long-running harnesses → orchestrator-worker, ~15x token cost of multi-agent, initializer/coder/verifier pattern, progress-file resume.
- CrewAI: hierarchical mode documented-broken; ~3x token overhead; Flows-only if ever used → relegated to optional adapter.
- Sandboxing: GitHub Agentic Workflows firewall, Infisical Agent Vault, Claude Code sandbox-runtime → zero-secret containers + injecting egress proxy.
- Memory: Anthropic + Letta converged on markdown-in-git; grep beat embeddings for code search.
- Models: LiteLLM aliases/virtual keys/budgets; static per-role routing + overrides is the proven pattern.
