import { HttpResponse, http } from "msw";
import type { components } from "../schema";
import { db } from "./db";
import { seed } from "./fixtures";
import { buildEventStream } from "./sse";

type WorkItemStatus = components["schemas"]["WorkItem"]["status"];

const BASE = "/api";

// ─── Envelope helpers ─────────────────────────────────────────────────────────

type Meta = { total: number; page_size: number; page_number: number };

const ok = (data: unknown, meta?: Meta) =>
  HttpResponse.json({ success: true, data, error: null, meta: meta ?? null });

const notFound = (msg = "not found") =>
  HttpResponse.json(
    { success: false, data: null, error: msg },
    { status: 404 },
  );

const pageMeta = (items: unknown[], pageSize = 50): Meta => ({
  total: items.length,
  page_size: pageSize,
  page_number: 1,
});

// ─── Live handlers ─────────────────────────────────────────────────────────────
// These paths are backed by the real backend when VITE_LIVE_API=true.
// In live mode only mockOnlyHandlers are registered in MSW so these routes
// pass through the Vite proxy to http://localhost:8000.
// Registration order matters: literal paths MUST come before parameterised
// siblings (e.g. /projects/:id/board before /projects/:id).

export const liveHandlers = [
  // ── Projects ────────────────────────────────────────────────────────────────

  http.get(`${BASE}/projects`, () =>
    ok(db.projects, pageMeta(db.projects)),
  ),

  http.post(`${BASE}/projects`, async ({ request }) => {
    const body = (await request.json()) as { name: string; repoUrl: string };
    const created = {
      id: `proj-${Date.now()}`,
      name: body.name,
      repoUrl: body.repoUrl,
      itemCount: 0,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    db.addProject(created);
    return HttpResponse.json(
      { success: true, data: created, error: null, meta: null },
      { status: 201 },
    );
  }),

  http.post(`${BASE}/projects/:id/work-items`, async ({ params, request }) => {
    const p = db.findProject(params.id as string);
    if (!p) return notFound();
    const body = (await request.json()) as Record<string, unknown>;
    const created = {
      id: `wi-${Date.now()}`,
      projectId: params.id as string,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      ...body,
    };
    db.addWorkItem(created as unknown as components["schemas"]["WorkItem"]);
    return HttpResponse.json(
      { success: true, data: created, error: null, meta: null },
      { status: 201 },
    );
  }),

  http.get(`${BASE}/projects/:id`, ({ params }) => {
    const p = db.findProject(params.id as string);
    return p ? ok(p) : notFound();
  }),

  http.patch(`${BASE}/projects/:id`, async ({ params, request }) => {
    const p = db.findProject(params.id as string);
    if (!p) return notFound();
    const body = (await request.json()) as Partial<{ name: string; repoUrl: string }>;
    return ok({ ...p, ...body, updatedAt: new Date().toISOString() });
  }),

  http.delete(`${BASE}/projects/:id`, ({ params }) => {
    const p = db.findProject(params.id as string);
    return p ? ok(null) : notFound();
  }),

  // ── Work items (global) ──────────────────────────────────────────────────────

  http.get(`${BASE}/work-items`, ({ request }) => {
    const url = new URL(request.url);
    const status = url.searchParams.get("status") as WorkItemStatus | null;
    const project = url.searchParams.get("project");
    const epic = url.searchParams.get("epic");
    let items = db.workItems;
    if (status) items = items.filter((w) => w.status === status);
    if (project) items = items.filter((w) => w.projectId === project);
    if (epic) items = items.filter((w) => w.epicId === epic);
    return ok(items, pageMeta(items));
  }),

  // Literal sub-paths before parameterised :id
  http.post(`${BASE}/work-items/:id/runs`, ({ params }) => {
    const w = db.findWorkItem(params.id as string);
    if (!w) return notFound();
    const now = new Date().toISOString();
    const run = {
      id: `run-${Date.now()}`,
      workItemId: w.id,
      projectId: w.projectId,
      autonomyLevel: "gated_all",
      status: "running",
      currentStage: "plan",
      stages: [{ stage: "plan", status: "running", role: "lead", startedAt: now, endedAt: null }],
      pendingGate: null,
      createdAt: now,
      updatedAt: now,
      startedAt: now,
      endedAt: null,
      tokenUsage: 0,
      cost: 0,
      prUrl: null,
    } as components["schemas"]["RunOut"];
    db.addRun(run);
    db.updateWorkItem(w.id, { status: "in_progress" });
    return HttpResponse.json({ success: true, data: run, error: null, meta: null }, { status: 201 });
  }),

  http.post(`${BASE}/work-items/:id/transition`, async ({ params, request }) => {
    const w = db.findWorkItem(params.id as string);
    if (!w) return notFound();
    const body = (await request.json()) as { status: WorkItemStatus };
    const updated = db.updateWorkItem(params.id as string, { status: body.status });
    return ok(updated);
  }),

  // ── Attachments (literal sub-paths before bare :id) ─────────────────────────

  http.get(`${BASE}/work-items/:id/attachments`, ({ params }) =>
    ok(db.listAttachments(params.id as string)),
  ),

  http.post(`${BASE}/work-items/:id/attachments`, async ({ params, request }) => {
    const form = await request.formData();
    const file = form.get("file") as File;
    const created = db.addAttachment({
      id: `att-${file.name}`,
      workItemId: params.id as string,
      filename: file.name,
      contentType: file.type || "application/octet-stream",
      size: file.size,
      url: `/work-items/${params.id}/attachments/att-${file.name}`,
      createdAt: new Date().toISOString(),
    });
    return HttpResponse.json({ success: true, data: created, error: null }, { status: 201 });
  }),

  http.delete(`${BASE}/work-items/:id/attachments/:attId`, ({ params }) => {
    db.deleteAttachment(params.attId as string);
    return ok({ deleted: params.attId });
  }),

  http.get(`${BASE}/work-items/:id`, ({ params }) => {
    const w = db.findWorkItem(params.id as string);
    return w ? ok(w) : notFound();
  }),

  http.patch(`${BASE}/work-items/:id`, async ({ params, request }) => {
    const body = (await request.json()) as Partial<components["schemas"]["WorkItem"]>;
    const updated = db.updateWorkItem(params.id as string, body);
    return updated ? ok(updated) : notFound();
  }),

  // ── Teams ─────────────────────────────────────────────────────────────────────

  http.get(`${BASE}/teams`, () => ok(seed.teams)),

  // ── Agent definitions ─────────────────────────────────────────────────────────

  http.get(`${BASE}/agent-definitions`, () => ok(seed.agentDefinitions)),

  http.patch(`${BASE}/agent-definitions/:id`, async ({ params, request }) => {
    const def = seed.agentDefinitions.find((d) => d.id === params.id);
    if (!def) return notFound();
    const body = (await request.json()) as Partial<components["schemas"]["AgentDefinition"]>;
    return ok({ ...def, ...body });
  }),

  // ── Secrets (owner-scoped, write-only) ──────────────────────────────────────────

  http.get(`${BASE}/secrets`, () => ok(db.listSecrets())),

  http.put(`${BASE}/secrets/:name`, async ({ params, request }) => {
    const name = params.name as string;
    if (!["anthropic_api_key", "github_token", "claude_oauth_token"].includes(name)) {
      return HttpResponse.json({ success: false, data: null, error: "unknown secret" }, { status: 422 });
    }
    const body = (await request.json()) as { value: string };
    return ok(db.setSecret(name, body.value));
  }),

  http.delete(`${BASE}/secrets/:name`, ({ params }) => ok(db.deleteSecret(params.name as string))),

  // ── Runs ──────────────────────────────────────────────────────────────────────
  // Now backed by the real backend (A3). In live mode these pass through to /api.
  // Literal + more-specific paths before the bare /:id catch-all.

  http.get(`${BASE}/runs`, ({ request }) => {
    const url = new URL(request.url);
    const workItem = url.searchParams.get("work_item");
    const runs = workItem ? db.runsForWorkItem(workItem) : db.runs;
    return ok(runs, pageMeta(runs));
  }),

  http.get(`${BASE}/runs/:id/events/stream`, ({ params }) => {
    const run = db.findRun(params.id as string);
    if (!run) return notFound();
    const events = db.eventsForRun(params.id as string);
    return new HttpResponse(buildEventStream(events), {
      headers: { "content-type": "text/event-stream" },
    });
  }),

  http.get(`${BASE}/runs/:id/events`, ({ params }) => {
    const run = db.findRun(params.id as string);
    if (!run) return notFound();
    const events = db.eventsForRun(params.id as string);
    return ok(events, pageMeta(events));
  }),

  http.post(`${BASE}/runs/:id/gate`, async ({ params, request }) => {
    const run = db.findRun(params.id as string);
    if (!run) return notFound();
    const body = (await request.json()) as { decision: "approve" | "reject" };
    const updated = db.updateRun(params.id as string, {
      status: body.decision === "approve" ? "running" : "failed",
      pendingGate: null,
    });
    return ok(updated);
  }),

  http.get(`${BASE}/runs/:id/activity`, () => ok([], pageMeta([]))),

  http.get(`${BASE}/runs/:id`, ({ params }) => {
    const run = db.findRun(params.id as string);
    return run ? ok(run) : notFound();
  }),

  // ── Agents ───────────────────────────────────────────────────────────────────

  http.get(`${BASE}/agents`, () => ok(seed.agents)),

  // ── Dashboard (live-backed) ───────────────────────────────────────────────────

  http.get(`${BASE}/dashboard/metrics`, () => ok(seed.metrics)),

  http.get(`${BASE}/dashboard/token-usage`, () => ok(seed.tokenUsagePoints)),

  // ── Budget (live-backed) ──────────────────────────────────────────────────────

  http.get(`${BASE}/budget`, () => ok(seed.budget)),

  // ── Activity ──────────────────────────────────────────────────────────────────

  http.get(`${BASE}/activity`, () => ok(seed.activityEvents)),

  // ── Threads ───────────────────────────────────────────────────────────────────
  // Backed by the real backend (A3+). In live mode these pass through to /api.
  // More-specific paths (/messages) must be listed before the bare /:id catch-all.

  http.get(`${BASE}/threads`, () => ok(seed.threads)),

  http.get(`${BASE}/threads/:id/messages`, ({ params }) => {
    const msgs = db.messagesForThread(params.id as string);
    return ok(msgs, pageMeta(msgs));
  }),

  http.get(`${BASE}/threads/:id/activity`, () => ok([], pageMeta([]))),

  http.get(`${BASE}/threads/:id`, ({ params }) => {
    const detail = db.threadDetail(params.id as string);
    return detail ? ok(detail) : notFound();
  }),

  http.post(`${BASE}/threads/:id/messages/:msgId/answer`, async ({ params, request }) => {
    const body = (await request.json()) as { option: string };
    const msg = db.resolveQuestion(params.msgId as string, body.option);
    if (!msg) return notFound();
    return ok(msg);
  }),

  http.post(`${BASE}/threads/:id/messages`, async ({ params, request }) => {
    const body = (await request.json()) as { content: string };
    const workItemId = params.id as string;
    const KNOWN_ROLES = ["lead", "architect", "backend", "frontend", "qa", "devops"];
    const seen = new Set<string>();
    const mentions = [...body.content.matchAll(/@([\w-]+)/g)]
      .map((m) => m[1])
      .filter((r) => {
        if (!KNOWN_ROLES.includes(r) || seen.has(r)) return false;
        seen.add(r);
        return true;
      });
    const msg: components["schemas"]["Message"] = {
      id: `msg-${Date.now()}`,
      threadId: workItemId,
      authorKind: "user",
      authorRole: null,
      model: null,
      kind: "text",
      content: body.content,
      mentions,
      payload: null,
      runId: null,
      createdAt: new Date().toISOString(),
    };
    db.addMessage(msg);

    // Project-level "chat with lead": simulate the lead orchestrator creating
    // work items and proposing a run, so the flow is demoable offline.
    if (workItemId.startsWith("project:")) {
      const projectId = workItemId.slice("project:".length);
      const t = Date.now();
      const now = () => new Date().toISOString();
      const epicId = `wi-${t}-e`;
      const taskId = `wi-${t}-t`;
      db.addWorkItem({
        id: epicId, projectId, type: "epic", title: body.content,
        status: "todo", priority: "medium", createdAt: now(), updatedAt: now(),
      } as unknown as components["schemas"]["WorkItem"]);
      db.addWorkItem({
        id: taskId, projectId, type: "task", title: `Implement: ${body.content}`,
        epicId, status: "todo", priority: "medium", createdAt: now(), updatedAt: now(),
      } as unknown as components["schemas"]["WorkItem"]);
      db.addMessage({
        id: `msg-${t}-r`, threadId: workItemId, authorKind: "agent", authorRole: "lead",
        model: null, kind: "text",
        content: `[lead] Created epic '${body.content}' and a task. Ready to start development.`,
        mentions: [], payload: null, runId: null, createdAt: now(),
      });
      db.addMessage({
        id: `msg-${t}-q`, threadId: workItemId, authorKind: "agent", authorRole: "lead",
        model: null, kind: "question", content: "Start development on these items?",
        mentions: [],
        payload: {
          options: [{ id: "approve", label: "Approve" }, { id: "reject", label: "Reject" }],
          run_proposal: true, work_item_ids: [taskId], resolved_option: null,
        },
        runId: null, createdAt: now(),
      });
    }

    return HttpResponse.json(
      { success: true, data: msg, error: null, meta: null },
      { status: 201 },
    );
  }),

  http.get(`${BASE}/threads/:id`, ({ params }) => {
    const workItemId = params.id as string;
    const thread = db.findThread(workItemId);
    if (!thread) return notFound();
    const filesWritten = db
      .messagesForThread(workItemId)
      .filter((m) => m.kind === "file_write")
      .map((m) => (m.payload ?? {}));
    return ok({ ...thread, filesWritten });
  }),
];

// ─── Mock-only handlers ────────────────────────────────────────────────────────
// These paths have NO real backend — always served by MSW regardless of mode.

export const mockOnlyHandlers = [
  // ── Mocked work-item and project endpoints ──────────────────────────────────
  // These have no real backend implementation (phase A2); always mocked.
  // Literal sub-paths before parameterised :id.

  http.get(`${BASE}/projects/:id/board`, ({ params }) => {
    const p = db.findProject(params.id as string);
    if (!p) return notFound();
    return ok(db.boardFor(params.id as string));
  }),
];

// ─── Combined (default — fully mocked) ────────────────────────────────────────
// Used by server.ts (node test setup) and browser.ts when VITE_LIVE_API != "true".

export const handlers = [...mockOnlyHandlers, ...liveHandlers];
