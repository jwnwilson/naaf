import type { components } from "../schema";
import { seed, threadConversationMap } from "./fixtures";

type Project = components["schemas"]["Project"];
type WorkItem = components["schemas"]["WorkItem"];
type AgentRun = components["schemas"]["AgentRun"];
type InboxItem = components["schemas"]["InboxItem"];
type Message = components["schemas"]["Message"];

// ─── Mutable in-memory stores ─────────────────────────────────────────────────
// Each store starts as a shallow copy of the seed so mutations don't affect the
// original fixture arrays.  db.reset() restores everything to seed state.

let projects: Project[] = [...seed.projects];
let workItems: WorkItem[] = [...seed.workItems];
let agentRuns: AgentRun[] = [...seed.agentRuns];
let inboxItems: InboxItem[] = [...seed.inboxItems];
let messages: Message[] = [...seed.messages];

// ─── Public db interface ──────────────────────────────────────────────────────

export const db = {
  // Getters return the current in-memory arrays
  get projects() {
    return projects;
  },
  get workItems() {
    return workItems;
  },
  get agentRuns() {
    return agentRuns;
  },
  get inboxItems() {
    return inboxItems;
  },
  get messages() {
    return messages;
  },

  // ─── Lookups ───────────────────────────────────────────────────────────────

  findProject: (id: string): Project | null =>
    projects.find((p) => p.id === id) ?? null,

  findWorkItem: (id: string): WorkItem | null =>
    workItems.find((w) => w.id === id) ?? null,

  findRun: (id: string): AgentRun | null =>
    agentRuns.find((r) => r.id === id) ?? null,

  findInboxItem: (id: string): InboxItem | null =>
    inboxItems.find((i) => i.id === id) ?? null,

  // All work items belonging to a project (the board tree)
  boardFor: (projectId: string): WorkItem[] =>
    workItems.filter((w) => w.projectId === projectId),

  // Messages for a thread, resolved via the thread → conversation mapping
  messagesForThread: (threadId: string): Message[] => {
    const convId = threadConversationMap[threadId];
    if (!convId) return [];
    return messages.filter((m) => m.conversationId === convId);
  },

  // ─── Mutations (immutable pattern: replace the array, never mutate items) ──

  markInboxRead: (id: string): void => {
    inboxItems = inboxItems.map((i) =>
      i.id === id ? { ...i, read: true } : i,
    );
  },

  markAllInboxRead: (): void => {
    inboxItems = inboxItems.map((i) => ({ ...i, read: true }));
  },

  updateWorkItem: (
    id: string,
    patch: Partial<WorkItem>,
  ): WorkItem | null => {
    workItems = workItems.map((w) =>
      w.id === id
        ? { ...w, ...patch, updatedAt: new Date().toISOString() }
        : w,
    );
    return workItems.find((w) => w.id === id) ?? null;
  },

  // ─── Reset (restore all stores to seed state) ─────────────────────────────

  reset: (): void => {
    projects = [...seed.projects];
    workItems = [...seed.workItems];
    agentRuns = [...seed.agentRuns];
    inboxItems = [...seed.inboxItems];
    messages = [...seed.messages];
  },
};
