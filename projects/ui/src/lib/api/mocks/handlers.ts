import { HttpResponse, http } from "msw";
import type { components } from "../schema";
import { db } from "./db";
import { seed } from "./fixtures";
import { buildRunStream } from "./sse";

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
  http.post(`${BASE}/work-items/:id/transition`, async ({ params, request }) => {
    const w = db.findWorkItem(params.id as string);
    if (!w) return notFound();
    const body = (await request.json()) as { status: WorkItemStatus };
    const updated = db.updateWorkItem(params.id as string, { status: body.status });
    return ok(updated);
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

  // ── Threads ───────────────────────────────────────────────────────────────────
  // Backed by the real backend (Task 5). In live mode these pass through to /api.

  http.get(`${BASE}/threads`, () => ok(seed.threads)),

  http.get(`${BASE}/threads/:id/messages`, ({ params }) => {
    const msgs = db.messagesForThread(params.id as string);
    return ok(msgs);
  }),

  http.post(`${BASE}/threads/:id/messages`, async ({ params, request }) => {
    const body = (await request.json()) as { content: string };
    const msg: components["schemas"]["Message"] = {
      id: `msg-${Date.now()}`,
      conversationId: `conv-${String(params.id).replace("thread-", "")}`,
      role: "user",
      agentId: null,
      content: body.content,
      attachments: null,
      createdAt: new Date().toISOString(),
    };
    return HttpResponse.json(
      { success: true, data: msg, error: null, meta: null },
      { status: 201 },
    );
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

  http.get(`${BASE}/work-items/:id/run`, ({ params }) => {
    const run = seed.agentRuns.find((r) => r.workItemId === params.id) ?? null;
    return ok(run);
  }),

  // ── Agents ───────────────────────────────────────────────────────────────────

  http.get(`${BASE}/agents`, () => ok(seed.agents)),

  // ── Runs ──────────────────────────────────────────────────────────────────────

  http.get(`${BASE}/runs`, () => ok(db.agentRuns, pageMeta(db.agentRuns))),

  http.get(`${BASE}/runs/:id`, ({ params }) => {
    const run = db.findRun(params.id as string);
    return run ? ok(run) : notFound();
  }),

  // Events history — returns empty list in mock mode; live data comes via SSE stream
  http.get(`${BASE}/runs/:id/events`, () => ok([], pageMeta([]))),

  http.get(`${BASE}/runs/:id/stream`, () =>
    new HttpResponse(buildRunStream(), {
      headers: { "content-type": "text/event-stream" },
    }),
  ),

  // ── Dashboard ─────────────────────────────────────────────────────────────────

  http.get(`${BASE}/dashboard/metrics`, () => ok(seed.metrics)),

  http.get(`${BASE}/dashboard/token-usage`, () => ok(seed.tokenUsagePoints)),

  // ── Activity ──────────────────────────────────────────────────────────────────

  http.get(`${BASE}/activity`, () => ok(seed.activityEvents)),

  // ── Budget ────────────────────────────────────────────────────────────────────

  http.get(`${BASE}/budget`, () => ok(seed.budget)),
];

// ─── Combined (default — fully mocked) ────────────────────────────────────────
// Used by server.ts (node test setup) and browser.ts when VITE_LIVE_API != "true".

export const handlers = [...mockOnlyHandlers, ...liveHandlers];
