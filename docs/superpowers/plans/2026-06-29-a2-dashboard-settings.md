# A2 Dashboard + Settings — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Dashboard (Screen E — metric cards, running-agents panel, token bar chart, activity feed) and Settings (Screen F — settings subnav, lead-agent card, subagents table), wired to the mock data layer.

**Architecture:** `DashboardScreen` composes a metric-cards row + running-agents panel + token chart + activity feed from `useDashboard`/`useAgents`/`useTokenUsage`/`useActivity`. `SettingsScreen` composes a settings subnav + lead-agent card + subagents table from `useAgentDefinitions`, with `Toggle`s for enable/disable (display-only for A2).

**Tech Stack:** Plan-1 `components/ui` (`MetricCard`, `Card`, `ProgressBar`, `PulseDot`, `Toggle`, `Button`, `Avatar`), Plan-2 `lib/api` hooks.

## Global Constraints

- pnpm; commands from `projects/ui/`. Compose existing primitives + hooks. Exact values in `docs/design/README.md` § "Screen E — Dashboard" and "Screen F — Settings". Cite the subsection.
- TypeScript strict; props typed; no `any`; types from `components["schemas"]` (`DashboardMetrics`, `TokenUsagePoint`, `ActivityEvent`, `Agent`, `AgentDefinition`). Tokens via Tailwind utilities. Immutable. Commit `<type>: <description>`; one per task. TDD. Keep `pnpm test`/`pnpm lint`/`pnpm build` green each task.
- If `useTokenUsage` / `useActivity` hooks don't exist yet, add them in `lib/api/hooks/` (over `/dashboard/token-usage` and `/activity`) following the existing hook pattern, and re-export from `hooks/index.ts`.
- Tests route through `createMemoryRouter(routes, {initialEntries:["/dashboard"]})` / `["/settings/agents"]`. The mock fixtures supply dashboard metrics, a token series, activity events, and agent definitions.
- Work in the `feat/a2-ui` worktree; Plans 1–6 are on this branch.

---

## File Structure

```
projects/ui/src/modules/dashboard/
  DashboardScreen.tsx      # replaces placeholder; cards + panels
  MetricCards.tsx          # 4 metric cards row
  RunningAgentsPanel.tsx   # running/idle agent rows
  TokenChart.tsx           # daily token bar chart
  ActivityFeed.tsx         # activity event rows
projects/ui/src/modules/settings/
  SettingsScreen.tsx       # replaces placeholder; subnav + cards
  SettingsSubnav.tsx       # 176px section nav
  LeadAgentCard.tsx        # lead agent config card
  SubagentsTable.tsx       # subagent rows + toggles
projects/ui/src/lib/api/hooks/ (useTokenUsage.ts, useActivity.ts if missing)
  (tests co-located)
```

---

### Task 1: Dashboard — metric cards + running-agents panel

**Files:** Create `modules/dashboard/MetricCards.tsx`, `RunningAgentsPanel.tsx` (+ tests); add `lib/api/hooks/useActivity.ts`/`useTokenUsage.ts` if missing.

**Interfaces:**
- Consumes: `useDashboard` (metrics), `useAgents`; Plan-1 `MetricCard`, `Card`, `ProgressBar`, `PulseDot`, `Button`.
- Produces:
  - `MetricCards()` — the 4-card grid per `docs/design/README.md` § Dashboard "Metric cards row" from `useDashboard()` (active agents, spend, tokens, counts). The spend card gets the accent border + progress bar.
  - `RunningAgentsPanel()` — the running-agents panel per § Dashboard (left column): running rows (`PulseDot` + name/task + mini `ProgressBar` + tokens + Pause `Button`), idle rows (outline dot + name + Assign), from `useAgents()`. Guarded.

- [ ] **Step 1: Write the failing tests**

`modules/dashboard/MetricCards.test.tsx`:
```tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../../lib/api/queryClient";
import { MetricCards } from "./MetricCards";

describe("MetricCards", () => {
  it("renders metric cards from the mock dashboard", async () => {
    render(
      <QueryClientProvider client={createQueryClient()}><MetricCards /></QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByText(/ACTIVE AGENTS|AGENTS/i)).toBeInTheDocument());
  });
});
```

`modules/dashboard/RunningAgentsPanel.test.tsx`:
```tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../../lib/api/queryClient";
import { RunningAgentsPanel } from "./RunningAgentsPanel";

describe("RunningAgentsPanel", () => {
  it("renders agent rows from the mock", async () => {
    render(
      <QueryClientProvider client={createQueryClient()}><RunningAgentsPanel /></QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getAllByRole("button").length).toBeGreaterThan(0));
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd projects/ui && pnpm test modules/dashboard/MetricCards modules/dashboard/RunningAgentsPanel`
Expected: FAIL — modules not found.

- [ ] **Step 3: Implement the hooks (if missing) + components** per README § Dashboard. Read `lib/api/hooks/` first; if `useDashboard` returns the metrics object, derive the 4 cards. Add `useTokenUsage`/`useActivity` hooks if absent (for Task 2). `RunningAgentsPanel` consumes `useAgents()`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd projects/ui && pnpm test modules/dashboard/MetricCards modules/dashboard/RunningAgentsPanel && pnpm lint`
Expected: PASS; lint clean.

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/modules/dashboard/MetricCards.tsx projects/ui/src/modules/dashboard/RunningAgentsPanel.tsx projects/ui/src/modules/dashboard/MetricCards.test.tsx projects/ui/src/modules/dashboard/RunningAgentsPanel.test.tsx projects/ui/src/lib/api/hooks
git commit -m "feat(ui): dashboard metric cards + running agents panel"
```

---

### Task 2: Dashboard — token chart + activity feed + DashboardScreen

**Files:** Create `modules/dashboard/TokenChart.tsx`, `ActivityFeed.tsx`; Modify `modules/dashboard/DashboardScreen.tsx` (replace placeholder) (+ tests)

**Interfaces:**
- Consumes: `useTokenUsage` (daily series), `useActivity`; `MetricCards`, `RunningAgentsPanel`; Plan-1 `Card`.
- Produces:
  - `TokenChart()` — the daily token bar chart per `docs/design/README.md` § Dashboard "Token chart": flexbox bars (`align-items:flex-end`), today's bar accent, day labels. From `useTokenUsage()`.
  - `ActivityFeed()` — the activity feed per § Dashboard: dot + text + timestamp rows from `useActivity()`.
  - `DashboardScreen()` — `MetricCards` row, then the two-column layout (`RunningAgentsPanel` | `TokenChart` over `ActivityFeed`), per § Dashboard. Replaces the placeholder.

- [ ] **Step 1: Write the failing test**

`modules/dashboard/DashboardScreen.test.tsx`:
```tsx
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../../lib/api/queryClient";
import { routes } from "../../app/routes";

describe("DashboardScreen", () => {
  it("renders metric cards, the agents panel and the token chart", async () => {
    const router = createMemoryRouter(routes, { initialEntries: ["/dashboard"] });
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByText(/AGENTS/i)).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm test modules/dashboard/DashboardScreen`
Expected: FAIL — placeholder heading still renders.

- [ ] **Step 3: Implement TokenChart + ActivityFeed + DashboardScreen** per README § Dashboard.

- [ ] **Step 4: Full gate**

Run: `cd projects/ui && pnpm test && pnpm lint && pnpm build`
Expected: all dashboard + prior tests pass; lint clean; build emits `dist/`; `git status` clean.

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/modules/dashboard/TokenChart.tsx projects/ui/src/modules/dashboard/ActivityFeed.tsx projects/ui/src/modules/dashboard/DashboardScreen.tsx projects/ui/src/modules/dashboard/DashboardScreen.test.tsx
git commit -m "feat(ui): dashboard token chart + activity feed + screen"
```

---

### Task 3: Settings (subnav + lead agent + subagents table) + full gate

**Files:** Create `modules/settings/SettingsSubnav.tsx`, `LeadAgentCard.tsx`, `SubagentsTable.tsx`; Modify `modules/settings/SettingsScreen.tsx` (replace placeholder) (+ tests)

**Interfaces:**
- Consumes: `useAgentDefinitions` (Plan 2); Plan-1 `Card`, `Avatar`, `Toggle`, `StatusBadge`, `Button`.
- Produces:
  - `SettingsSubnav({ active }: { active: string })` — the 176px section nav per `docs/design/README.md` § Settings "Settings subnav" (section labels + items; active accent).
  - `LeadAgentCard({ agent }: { agent: AgentDefinition })` — the lead-agent card per § Settings: avatar + name + ACTIVE badge, model + token-limit fields, system-prompt textarea (display-only).
  - `SubagentsTable({ agents }: { agents: AgentDefinition[] })` — the subagents table per § Settings: rows (avatar · name · model · token limit · enabled `Toggle`). The toggle is display-only/local for A2.
  - `SettingsScreen()` — subnav + `LeadAgentCard` (the lead-role agent) + `SubagentsTable` (the rest), from `useAgentDefinitions()`. Replaces the placeholder.

- [ ] **Step 1: Write the failing test**

`modules/settings/SettingsScreen.test.tsx`:
```tsx
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../../lib/api/queryClient";
import { routes } from "../../app/routes";

describe("SettingsScreen", () => {
  it("renders the agent settings with toggles from the mock", async () => {
    const router = createMemoryRouter(routes, { initialEntries: ["/settings/agents"] });
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getAllByRole("switch").length).toBeGreaterThan(0));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm test modules/settings/SettingsScreen`
Expected: FAIL — placeholder heading still renders.

- [ ] **Step 3: Implement SettingsSubnav + LeadAgentCard + SubagentsTable + SettingsScreen** per README § Settings. The lead agent is the `AgentDefinition` whose `role === "lead"` (fallback: first); the rest go in the table. Toggles use local state (display-only).

- [ ] **Step 4: Full gate**

Run: `cd projects/ui && pnpm test && pnpm lint && pnpm build`
Expected: all settings + prior tests pass; lint clean; build emits `dist/`; `git status` clean.

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/modules/settings projects/ui/src/modules/settings/SettingsScreen.test.tsx
git commit -m "feat(ui): settings screen (lead agent + subagents)"
```

---

## Self-Review

**1. Spec coverage (against spec §7 Dashboard/Settings + handoff § Screen E/F):** Task 1 = metric cards + running-agents panel. Task 2 = token chart + activity feed + DashboardScreen (+ the `useTokenUsage`/`useActivity` hooks if missing). Task 3 = settings subnav + lead-agent card + subagents table + SettingsScreen + full gate. Settings edits/toggles are display-only for A2 (their PATCH backend is C). Sidebar already links to both routes (Plan 3).

**2. Placeholder scan:** No "TBD"/"implement later" as engineering placeholders. Display-only settings edits are scoped A2 deliverables. Exact Screen E/F values reference `docs/design/README.md` § Screen E/F (in-repo). The `useTokenUsage`/`useActivity` hooks follow the established Plan-2 hook pattern.

**3. Type consistency:** `DashboardMetrics`/`TokenUsagePoint`/`ActivityEvent`/`Agent`/`AgentDefinition` from `components["schemas"]`. `MetricCards`/`RunningAgentsPanel`/`TokenChart`/`ActivityFeed` are no-prop screen sections (they call hooks); `LeadAgentCard({agent})`/`SubagentsTable({agents})`/`SettingsSubnav({active})` take typed props. `useAgentDefinitions` (Plan 2) returns `{data:{results,meta}}` consumed by Settings. Routes `/dashboard` and `/settings/agents` match the Plan-3 route table + sidebar links.
