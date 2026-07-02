import type { components } from "../schema";
import { seed, threadConversationMap } from "./fixtures";

type Project = components["schemas"]["Project"];
type WorkItem = components["schemas"]["WorkItem"];
type RunOut = components["schemas"]["RunOut"];
type RunEventOut = components["schemas"]["RunEventOut"];
type Message = components["schemas"]["Message"];

// ─── Mutable in-memory stores ─────────────────────────────────────────────────
// Each store starts as a DEEP clone of the seed so mutations never alias the
// original fixture objects.  db.reset() restores everything to seed state and
// is called between tests (see src/test/setup.ts).

const clone = <T>(items: T[]): T[] => structuredClone(items);

let projects: Project[] = clone(seed.projects);
let workItems: WorkItem[] = clone(seed.workItems);
let runs: RunOut[] = clone(seed.runs);
let messages: Message[] = clone(seed.messages);

// ─── Public db interface ──────────────────────────────────────────────────────

export const db = {
  // Getters return the current in-memory arrays
  get projects() {
    return projects;
  },
  get workItems() {
    return workItems;
  },
  get runs() {
    return runs;
  },
  get messages() {
    return messages;
  },

  // ─── Lookups ───────────────────────────────────────────────────────────────

  findProject: (id: string): Project | null =>
    projects.find((p) => p.id === id) ?? null,

  findWorkItem: (id: string): WorkItem | null =>
    workItems.find((w) => w.id === id) ?? null,

  findRun: (id: string): RunOut | null =>
    runs.find((r) => r.id === id) ?? null,

  // Runs for a work item, newest first
  runsForWorkItem: (workItemId: string): RunOut[] =>
    [...runs.filter((r) => r.workItemId === workItemId)].sort(
      (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
    ),

  // Events for a run (read from seed — events are not mutated in mock mode)
  eventsForRun: (runId: string): RunEventOut[] =>
    seed.runEvents.filter((e) => e.runId === runId),

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

  updateRun: (
    id: string,
    patch: Partial<RunOut>,
  ): RunOut | null => {
    runs = runs.map((r) =>
      r.id === id
        ? { ...r, ...patch, updatedAt: new Date().toISOString() }
        : r,
    );
    return runs.find((r) => r.id === id) ?? null;
  },

  // ─── Reset (restore all stores to seed state) ─────────────────────────────

  reset: (): void => {
    projects = clone(seed.projects);
    workItems = clone(seed.workItems);
    runs = clone(seed.runs);
    messages = clone(seed.messages);
  },
};
