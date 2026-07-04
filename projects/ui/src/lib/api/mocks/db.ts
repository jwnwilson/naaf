import type { components } from "../schema";
import type { Attachment } from "../hooks/useAttachments";
import { seed } from "./fixtures";

type Project = components["schemas"]["Project"];
type WorkItem = components["schemas"]["WorkItem"];
type RunOut = components["schemas"]["RunOut"];
type RunEventOut = components["schemas"]["RunEventOut"];
type Message = components["schemas"]["Message"];
type Thread = components["schemas"]["Thread"];
type MockAttachment = Attachment & { workItemId: string };

// ─── Mutable in-memory stores ─────────────────────────────────────────────────
// Each store starts as a DEEP clone of the seed so mutations never alias the
// original fixture objects.  db.reset() restores everything to seed state and
// is called between tests (see src/test/setup.ts).

const clone = <T>(items: T[]): T[] => structuredClone(items);

type Secret = components["schemas"]["SecretOut"];

const SECRET_NAMES = ["anthropic_api_key", "github_token", "claude_oauth_token"] as const;

let projects: Project[] = clone(seed.projects);
let workItems: WorkItem[] = clone(seed.workItems);
let runs: RunOut[] = clone(seed.runs);
let messages: Message[] = clone(seed.messages);
let attachments: MockAttachment[] = clone(seed.attachments);
let secretHints: Record<string, string> = {};  // name -> hint; presence = isSet

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

  // Thread for a work item
  findThread: (workItemId: string): Thread | null =>
    seed.threads.find((t) => t.workItemId === workItemId) ?? null,

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

  // Messages for a work-item thread, keyed by threadId (= workItemId)
  messagesForThread: (workItemId: string): Message[] =>
    messages.filter((m) => m.threadId === workItemId),

  // ─── Mutations (immutable pattern: replace the array, never mutate items) ──

  // Append a new project (immutable: replace the array)
  addProject: (project: Project): Project => {
    projects = [...projects, project];
    return project;
  },

  // Append a new work item and bump its parent project's itemCount
  addWorkItem: (item: WorkItem): WorkItem => {
    workItems = [...workItems, item];
    projects = projects.map((p) =>
      p.id === item.projectId ? { ...p, itemCount: p.itemCount + 1 } : p,
    );
    return item;
  },

  updateWorkItem: (
    id: string,
    patch: Partial<WorkItem>,
  ): WorkItem | null => {
    workItems = workItems.map((w) =>
      w.id === id ? { ...w, ...patch, updatedAt: new Date().toISOString() } : w,
    );
    return workItems.find((w) => w.id === id) ?? null;
  },

  updateRun: (id: string, patch: Partial<RunOut>): RunOut | null => {
    runs = runs.map((r) =>
      r.id === id ? { ...r, ...patch, updatedAt: new Date().toISOString() } : r,
    );
    return runs.find((r) => r.id === id) ?? null;
  },

  addRun: (run: RunOut): RunOut => {
    runs = [...runs, run];
    return run;
  },

  addMessage: (msg: Message): Message => {
    messages = [...messages, msg];
    return msg;
  },

  resolveQuestion: (msgId: string, option: string): Message | null => {
    const existing = messages.find((m) => m.id === msgId);
    if (!existing) return null;
    messages = messages.map((m) =>
      m.id === msgId
        ? { ...m, payload: { ...(m.payload ?? {}), resolved_option: option } }
        : m,
    );
    return messages.find((m) => m.id === msgId) ?? null;
  },

  // ─── Attachment store ──────────────────────────────────────────────────────

  listAttachments: (workItemId: string): MockAttachment[] =>
    attachments.filter((a) => a.workItemId === workItemId),

  addAttachment: (a: MockAttachment): MockAttachment => {
    attachments = [...attachments, a];
    return a;
  },

  deleteAttachment: (id: string): void => {
    attachments = attachments.filter((a) => a.id !== id);
  },

  // ─── Secrets (write-only; never store the raw value) ──────────────────────

  listSecrets: (): Secret[] =>
    SECRET_NAMES.map((name) => ({
      name,
      isSet: name in secretHints,
      hint: secretHints[name] ?? "",
    })),

  setSecret: (name: string, value: string): Secret => {
    secretHints = { ...secretHints, [name]: value.slice(-4) };
    return { name, isSet: true, hint: secretHints[name] };
  },

  deleteSecret: (name: string): Secret => {
    const rest = { ...secretHints };
    delete rest[name];
    secretHints = rest;
    return { name, isSet: false, hint: "" };
  },

  // ─── Reset (restore all stores to seed state) ─────────────────────────────

  reset: (): void => {
    projects = clone(seed.projects);
    workItems = clone(seed.workItems);
    runs = clone(seed.runs);
    messages = clone(seed.messages);
    attachments = clone(seed.attachments);
    secretHints = {};
  },
};
