import type { components } from "../../schema";

type Agent = components["schemas"]["Agent"];
type Project = components["schemas"]["Project"];
type WorkItem = components["schemas"]["WorkItem"];
type Team = components["schemas"]["Team"];
type AgentDefinition = components["schemas"]["AgentDefinition"];
type RunOut = components["schemas"]["RunOut"];
type RunEventOut = components["schemas"]["RunEventOut"];
type Message = components["schemas"]["Message"];
type Thread = components["schemas"]["Thread"];
type DashboardMetrics = components["schemas"]["DashboardMetrics"];
type TokenUsagePoint = components["schemas"]["TokenUsagePoint"];
type ActivityEvent = components["schemas"]["ActivityEvent"];
type Budget = components["schemas"]["Budget"];

// ─── Agents ──────────────────────────────────────────────────────────────────

const agents: Agent[] = [
  {
    id: "agent-1",
    name: "Lead Agent",
    type: "lead",
    model: "claude-sonnet-4-6",
    status: "running",
    currentItemId: "wi-task-3",
    progress: 0.65,
    tokenUsage: 12400,
    tokenLimit: 50000,
  },
  {
    id: "agent-2",
    name: "Build Agent",
    type: "sub",
    model: "claude-haiku-4-5",
    status: "idle",
    currentItemId: null,
    progress: null,
    tokenUsage: 3200,
    tokenLimit: 30000,
  },
  {
    id: "agent-3",
    name: "QA Agent",
    type: "sub",
    model: "claude-haiku-4-5",
    status: "paused",
    currentItemId: "wi-task-4",
    progress: 0.3,
    tokenUsage: 8100,
    tokenLimit: 30000,
  },
];

// ─── Projects ─────────────────────────────────────────────────────────────────

const projects: Project[] = [
  {
    id: "proj-1",
    name: "NAAF Core Platform",
    repoUrl: "https://github.com/acme/naaf-core",
    itemCount: 8,
    createdAt: "2026-06-01T09:00:00Z",
    updatedAt: "2026-06-29T14:30:00Z",
  },
  {
    id: "proj-2",
    name: "NAAF Dashboard UI",
    repoUrl: "https://github.com/acme/naaf-ui",
    itemCount: 3,
    createdAt: "2026-06-10T11:00:00Z",
    updatedAt: "2026-06-28T16:00:00Z",
  },
];

// ─── Work items ───────────────────────────────────────────────────────────────
// proj-1: epics → features → tasks spanning all 5 statuses
// proj-2: simpler tree, all done

const workItems: WorkItem[] = [
  // proj-1 — epic (backlog)
  {
    id: "wi-epic-1",
    type: "epic",
    title: "Agent Orchestration Foundation",
    status: "backlog",
    priority: "high",
    projectId: "proj-1",
    epicId: null,
    featureId: null,
    tokenUsageThisRun: null,
    tokenUsageAllRuns: null,
    tokenLimit: null,
    spec: "Build the core orchestration layer for managing agent workflows.",
    attachments: null,
    createdAt: "2026-06-01T09:00:00Z",
    updatedAt: "2026-06-01T09:00:00Z",
  },
  // proj-1 — feature (todo)
  {
    id: "wi-feat-1",
    type: "feature",
    title: "Temporal Workflow Runner",
    status: "todo",
    priority: "high",
    projectId: "proj-1",
    epicId: "wi-epic-1",
    featureId: null,
    tokenUsageThisRun: null,
    tokenUsageAllRuns: null,
    tokenLimit: null,
    spec: "Implement durable workflow execution via Temporal.",
    attachments: null,
    createdAt: "2026-06-02T09:00:00Z",
    updatedAt: "2026-06-02T09:00:00Z",
  },
  // proj-1 — feature (in_progress)
  {
    id: "wi-feat-2",
    type: "feature",
    title: "Agent Sandbox & Egress Control",
    status: "in_progress",
    priority: "urgent",
    projectId: "proj-1",
    epicId: "wi-epic-1",
    featureId: null,
    tokenUsageThisRun: 5000,
    tokenUsageAllRuns: 12000,
    tokenLimit: 50000,
    spec: "Containerised sandbox with controlled network egress.",
    attachments: null,
    createdAt: "2026-06-03T09:00:00Z",
    updatedAt: "2026-06-29T10:00:00Z",
  },
  // proj-1 — task (backlog)
  {
    id: "wi-task-1",
    type: "task",
    title: "Set up Temporal dev server",
    status: "backlog",
    priority: "medium",
    projectId: "proj-1",
    epicId: "wi-epic-1",
    featureId: "wi-feat-1",
    tokenUsageThisRun: null,
    tokenUsageAllRuns: null,
    tokenLimit: null,
    spec: null,
    attachments: null,
    createdAt: "2026-06-04T09:00:00Z",
    updatedAt: "2026-06-04T09:00:00Z",
  },
  // proj-1 — task (todo)
  {
    id: "wi-task-2",
    type: "task",
    title: "Define workflow activities",
    status: "todo",
    priority: "medium",
    projectId: "proj-1",
    epicId: "wi-epic-1",
    featureId: "wi-feat-1",
    tokenUsageThisRun: null,
    tokenUsageAllRuns: null,
    tokenLimit: null,
    spec: null,
    attachments: null,
    createdAt: "2026-06-04T10:00:00Z",
    updatedAt: "2026-06-04T10:00:00Z",
  },
  // proj-1 — task (in_progress, assigned to running agent)
  {
    id: "wi-task-3",
    type: "task",
    title: "Implement Docker sandbox container",
    status: "in_progress",
    priority: "urgent",
    projectId: "proj-1",
    epicId: "wi-epic-1",
    featureId: "wi-feat-2",
    assignedAgent: agents[0],
    tokenUsageThisRun: 4800,
    tokenUsageAllRuns: 9600,
    tokenLimit: 20000,
    spec: "Create the Docker-based sandbox for agent code execution.",
    attachments: null,
    createdAt: "2026-06-05T09:00:00Z",
    updatedAt: "2026-06-29T14:00:00Z",
  },
  // proj-1 — task (in_review, assigned to paused agent)
  {
    id: "wi-task-4",
    type: "task",
    title: "Implement network egress proxy",
    status: "in_review",
    priority: "high",
    projectId: "proj-1",
    epicId: "wi-epic-1",
    featureId: "wi-feat-2",
    assignedAgent: agents[2],
    tokenUsageThisRun: 2200,
    tokenUsageAllRuns: 7800,
    tokenLimit: 20000,
    spec: "Proxy to control which endpoints agents can reach.",
    attachments: null,
    createdAt: "2026-06-06T09:00:00Z",
    updatedAt: "2026-06-28T16:00:00Z",
  },
  // proj-1 — task (done)
  {
    id: "wi-task-5",
    type: "task",
    title: "Write sandbox integration tests",
    status: "done",
    priority: "medium",
    projectId: "proj-1",
    epicId: "wi-epic-1",
    featureId: "wi-feat-2",
    tokenUsageThisRun: null,
    tokenUsageAllRuns: 15000,
    tokenLimit: 20000,
    spec: null,
    attachments: null,
    createdAt: "2026-06-07T09:00:00Z",
    updatedAt: "2026-06-25T12:00:00Z",
  },
  // proj-2 — epic (in_review)
  {
    id: "wi-epic-2",
    type: "epic",
    title: "Dashboard MVP",
    status: "in_review",
    priority: "high",
    projectId: "proj-2",
    epicId: null,
    featureId: null,
    tokenUsageThisRun: null,
    tokenUsageAllRuns: null,
    tokenLimit: null,
    spec: "Build the React dashboard UI for NAAF.",
    attachments: null,
    createdAt: "2026-06-10T09:00:00Z",
    updatedAt: "2026-06-28T10:00:00Z",
  },
  // proj-2 — feature (done)
  {
    id: "wi-feat-3",
    type: "feature",
    title: "Board Kanban View",
    status: "done",
    priority: "high",
    projectId: "proj-2",
    epicId: "wi-epic-2",
    featureId: null,
    tokenUsageThisRun: null,
    tokenUsageAllRuns: 22000,
    tokenLimit: 30000,
    spec: "Drag-and-drop kanban board for work items.",
    attachments: null,
    createdAt: "2026-06-11T09:00:00Z",
    updatedAt: "2026-06-26T14:00:00Z",
  },
  // proj-2 — task (done)
  {
    id: "wi-task-6",
    type: "task",
    title: "Implement drag-and-drop columns",
    status: "done",
    priority: "medium",
    projectId: "proj-2",
    epicId: "wi-epic-2",
    featureId: "wi-feat-3",
    tokenUsageThisRun: null,
    tokenUsageAllRuns: 8500,
    tokenLimit: 15000,
    spec: null,
    attachments: null,
    createdAt: "2026-06-12T09:00:00Z",
    updatedAt: "2026-06-24T15:00:00Z",
  },
];

// ─── Teams ───────────────────────────────────────────────────────────────────

const teams: Team[] = [{ id: "team-1", name: "Core Dev Team" }];

// ─── Agent definitions ────────────────────────────────────────────────────────

const agentDefinitions: AgentDefinition[] = [
  {
    id: "agentdef-lead",
    teamId: "team-1",
    role: "lead",
    model: "claude-sonnet-4-6",
    tokenLimit: 50000,
    systemPrompt:
      "You are the lead agent responsible for orchestrating the development team.",
    enabled: true,
  },
  {
    id: "agentdef-sub",
    teamId: "team-1",
    role: "engineer",
    model: "claude-haiku-4-5",
    tokenLimit: 30000,
    systemPrompt: null,
    enabled: true,
  },
];

// ─── Runs ─────────────────────────────────────────────────────────────────────
// run-1: active run, no pending gate (implement stage)
// run-2: awaiting_gate at the plan gate checkpoint

const runs: RunOut[] = [
  {
    id: "run-1",
    workItemId: "wi-task-3",
    projectId: "proj-1",
    autonomyLevel: "supervised",
    status: "running",
    currentStage: "implement",
    stages: [
      { stage: "plan", status: "passed", role: null, startedAt: "2026-06-29T13:00:00Z", endedAt: "2026-06-29T13:02:00Z" },
      { stage: "implement", status: "running", role: null, startedAt: "2026-06-29T13:02:00Z", endedAt: null },
      { stage: "verify", status: "pending", role: null, startedAt: null, endedAt: null },
      { stage: "pr", status: "pending", role: null, startedAt: null, endedAt: null },
      { stage: "learn", status: "pending", role: null, startedAt: null, endedAt: null },
    ],
    pendingGate: null,
    createdAt: "2026-06-29T13:00:00Z",
    updatedAt: "2026-06-29T13:10:00Z",
    startedAt: "2026-06-29T13:00:00Z",
    endedAt: null,
    tokenUsage: 12400,
    cost: 0.0372,
  },
  {
    id: "run-2",
    workItemId: "wi-task-4",
    projectId: "proj-1",
    autonomyLevel: "supervised",
    status: "awaiting_gate",
    currentStage: "plan",
    stages: [
      { stage: "plan", status: "passed", role: null, startedAt: "2026-06-28T15:00:00Z", endedAt: "2026-06-28T15:10:00Z" },
      { stage: "implement", status: "pending", role: null, startedAt: null, endedAt: null },
      { stage: "verify", status: "pending", role: null, startedAt: null, endedAt: null },
      { stage: "pr", status: "pending", role: null, startedAt: null, endedAt: null },
      { stage: "learn", status: "pending", role: null, startedAt: null, endedAt: null },
    ],
    pendingGate: { kind: "plan", stage: "plan" },
    createdAt: "2026-06-28T15:00:00Z",
    updatedAt: "2026-06-28T15:10:00Z",
    startedAt: "2026-06-28T15:00:00Z",
    endedAt: null,
    tokenUsage: 2200,
    cost: 0.0066,
  },
];

// run events: a log event and a stage_passed event (with tokens payload) for run-1
const runEvents: RunEventOut[] = [
  {
    id: "revt-1",
    runId: "run-1",
    seq: 1,
    stage: "plan",
    role: null,
    type: "log",
    payload: { message: "Starting run for wi-task-3", level: "info" },
    createdAt: "2026-06-29T13:00:01Z",
  },
  {
    id: "revt-2",
    runId: "run-1",
    seq: 2,
    stage: "plan",
    role: null,
    type: "stage_passed",
    payload: { tokens: 3200 },
    createdAt: "2026-06-29T13:02:00Z",
  },
  {
    id: "revt-3",
    runId: "run-1",
    seq: 3,
    stage: "implement",
    role: null,
    type: "log",
    payload: { message: "Generating implementation...", level: "info" },
    createdAt: "2026-06-29T13:10:00Z",
  },
];

// ─── Threads & messages ───────────────────────────────────────────────────────

const threads: Thread[] = [
  {
    id: "thread-1",
    agentId: "agent-1",
    workItemId: "wi-task-3",
    createdAt: "2026-06-29T13:00:00Z",
  },
];

// Map threadId → conversationId for message lookup.
// inbox-2/3/4 use their conversationId directly as the thread ID (self-mapped).
export const threadConversationMap: Record<string, string> = {
  "thread-1": "conv-1",
  "conv-2": "conv-2",
  "conv-3": "conv-3",
  "conv-4": "conv-4",
};

const messages: Message[] = [
  // ── conv-1: Docker sandbox PR (inbox-1) ──────────────────────────────────────
  {
    id: "msg-1",
    conversationId: "conv-1",
    role: "user",
    agentId: null,
    content:
      "Please implement the Docker sandbox container for wi-task-3. Focus on security and isolation.",
    attachments: null,
    createdAt: "2026-06-29T13:00:00Z",
  },
  {
    id: "msg-2",
    conversationId: "conv-1",
    role: "lead_agent",
    agentId: "agent-1",
    content:
      "I'll start by analysing the existing architecture and then implement the sandbox. Give me a moment to read the codebase.",
    attachments: null,
    createdAt: "2026-06-29T13:00:30Z",
  },
  {
    id: "msg-3",
    conversationId: "conv-1",
    role: "agent",
    agentId: "agent-1",
    content:
      "I've analysed the codebase. Plan: 1) Create a Docker image based on python:3.12-slim, 2) Add a non-root user, 3) Mount workspace read-only, 4) Restrict network access.",
    attachments: null,
    createdAt: "2026-06-29T13:02:00Z",
  },

  // ── conv-2: Egress proxy review (inbox-2) ────────────────────────────────────
  {
    id: "msg-4",
    conversationId: "conv-2",
    role: "agent",
    agentId: "agent-3",
    content:
      "The network egress proxy implementation is ready for review. I changed 3 files (+247 lines). The proxy intercepts outbound requests and validates them against the allowlist before forwarding.",
    attachments: null,
    createdAt: "2026-06-28T16:00:00Z",
  },
  {
    id: "msg-5",
    conversationId: "conv-2",
    role: "user",
    agentId: null,
    content:
      "Thanks. Please make sure the allowlist is loaded from config, not hardcoded. Otherwise looks good.",
    attachments: null,
    createdAt: "2026-06-28T16:20:00Z",
  },

  // ── conv-3: Integration tests run complete (inbox-3) ─────────────────────────
  {
    id: "msg-6",
    conversationId: "conv-3",
    role: "agent",
    agentId: "agent-2",
    content:
      "Run complete for wi-task-5. All 24 integration tests are passing. Token usage: 15,000. The sandbox test suite covers container startup, file-system isolation, and network egress blocking.",
    attachments: null,
    createdAt: "2026-06-25T12:00:00Z",
  },
  {
    id: "msg-7",
    conversationId: "conv-3",
    role: "user",
    agentId: null,
    content: "Great work. Marking this task as done.",
    attachments: null,
    createdAt: "2026-06-25T12:05:00Z",
  },

  // ── conv-4: Board kanban feature resolved (inbox-4) ──────────────────────────
  {
    id: "msg-8",
    conversationId: "conv-4",
    role: "agent",
    agentId: "agent-2",
    content:
      "Feature wi-feat-3 (Board Kanban View) is complete. PR #42 has been merged. All drag-and-drop columns are functional and the design matches the spec.",
    attachments: null,
    createdAt: "2026-06-26T14:00:00Z",
  },
  {
    id: "msg-9",
    conversationId: "conv-4",
    role: "user",
    agentId: null,
    content: "Confirmed — closing the feature. Nice work on the drop animations.",
    attachments: null,
    createdAt: "2026-06-26T14:10:00Z",
  },
];

// ─── Dashboard ────────────────────────────────────────────────────────────────

const metrics: DashboardMetrics = {
  activeAgents: 1,
  totalSpend: 42.85,
  totalTokens: 87500,
  projectCount: 2,
  workItemCount: 11,
};

// ~7-day daily token usage series
const BASE_DATE = new Date("2026-06-29T00:00:00Z");
const tokenUsagePoints: TokenUsagePoint[] = Array.from({ length: 7 }, (_, i) => {
  const d = new Date(BASE_DATE);
  d.setUTCDate(BASE_DATE.getUTCDate() - (6 - i));
  return {
    day: d.toISOString().split("T")[0],
    tokens: 8000 + Math.round(Math.sin(i * 0.9) * 2500 + i * 1400),
  };
});

const activityEvents: ActivityEvent[] = [
  {
    id: "evt-1",
    type: "run_complete",
    description: "Run completed for wi-task-5 (Write sandbox integration tests)",
    agentId: "agent-2",
    workItemId: "wi-task-5",
    createdAt: "2026-06-25T12:00:00Z",
  },
  {
    id: "evt-2",
    type: "status_change",
    description: "wi-task-4 moved from in_progress to in_review",
    agentId: "agent-3",
    workItemId: "wi-task-4",
    createdAt: "2026-06-28T16:00:00Z",
  },
  {
    id: "evt-3",
    type: "agent_write",
    description: "agent-1 wrote docker/sandbox/Dockerfile for wi-task-3",
    agentId: "agent-1",
    workItemId: "wi-task-3",
    createdAt: "2026-06-29T13:05:10Z",
  },
  {
    id: "evt-4",
    type: "run_failed",
    description: "Run failed for wi-epic-2 due to context limit exceeded",
    agentId: "agent-2",
    workItemId: "wi-epic-2",
    createdAt: "2026-06-27T09:30:00Z",
  },
];

// Budget near the threshold (87.5% utilisation)
const budget: Budget = {
  used: 87500,
  limit: 100000,
};

// ─── Seed export ──────────────────────────────────────────────────────────────

export const seed = {
  agents,
  projects,
  workItems,
  teams,
  agentDefinitions,
  runs,
  runEvents,
  threads,
  messages,
  metrics,
  tokenUsagePoints,
  activityEvents,
  budget,
};
