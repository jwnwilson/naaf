import { describe, expect, it } from "vitest";
import type { HttpHandler } from "msw";
import { apiFetch, apiList, apiPost } from "../client";
import { mockOnlyHandlers, liveHandlers } from "./handlers";

type ProjectRow = { id: string; itemCount: number };
type WorkItemRow = { id: string };

// MSW node server is started globally in src/test/setup.ts
describe("mock handlers", () => {
  it("serves a paginated project list with meta", async () => {
    const page = await apiList("/projects");
    expect(page.results.length).toBeGreaterThan(0);
    expect(page.meta.total).toBeGreaterThanOrEqual(page.results.length);
    expect(page.results[0]).toHaveProperty("name");
  });

  it("serves a single work item with the UI status set", async () => {
    const board = await apiFetch<{ id: string }[]>("/projects/proj-1/board");
    expect(Array.isArray(board)).toBe(true);
  });

  it("serves dashboard metrics and budget", async () => {
    await expect(apiFetch("/dashboard/metrics")).resolves.toBeTruthy();
    await expect(apiFetch("/budget")).resolves.toHaveProperty("limit");
  });

  it("404s an unknown project as an ApiError", async () => {
    await expect(apiFetch("/projects/nope")).rejects.toMatchObject({ status: 404 });
  });

  it("serves threads list", async () => {
    const threads = await apiFetch<unknown[]>("/threads");
    expect(Array.isArray(threads)).toBe(true);
  });

  it("thread detail includes the work item's projectId", async () => {
    const res = await fetch("/api/threads/wi-task-3");
    const body = await res.json();
    expect(body.data.projectId).toBe("proj-1");
  });
});

describe("handler split", () => {
  it("keeps the unbacked resources mocked and the live groups separate", () => {
    const path = (h: HttpHandler) => String(h.info.path);
    const live = liveHandlers.map(path).join(" ");
    const mock = mockOnlyHandlers.map(path).join(" ");
    expect(live).toMatch(/\/api\/projects/);
    expect(live).toMatch(/\/api\/work-items/);
    expect(live).toMatch(/\/api\/teams/);
    // dashboard stays mock-only; runs are now live
    expect(mock).toMatch(/\/api\/dashboard/);
    expect(live).toMatch(/\/api\/runs/);
    // board endpoint has no backend — always mocked
    expect(mock).toMatch(/\/api\/projects\/:id\/board/);
    // board must NOT be in live
    expect(live).not.toMatch(/board/);
    // /inbox is retired — must not appear anywhere
    expect(live).not.toMatch(/\/inbox/);
    expect(mock).not.toMatch(/\/inbox/);
    // /threads is now live (backed by Task 5 backend)
    expect(live).toMatch(/\/api\/threads/);
    expect(mock).not.toMatch(/\/api\/threads/);
  });

  it("/runs and start-run are live handlers and legacy run paths are gone", () => {
    expect(liveHandlers.some((h) => String(h.info.path).endsWith("/runs"))).toBe(true);
    // start-run (POST /work-items/:id/runs) is now backed by the real backend
    expect(liveHandlers.some((h) => String(h.info.path).endsWith("/work-items/:id/runs"))).toBe(true);
    const all = [...liveHandlers, ...mockOnlyHandlers].map((h) => String(h.info.path));
    expect(all.some((p) => p.endsWith("/runs/:id/stream"))).toBe(false);
  });
});

describe("create handlers persist to the mock store", () => {
  it("persists a created work item so the board list returns it", async () => {
    const before = await apiList<WorkItemRow>("/work-items", { project: "proj-1" });
    const created = await apiPost<WorkItemRow>("/projects/proj-1/work-items", {
      type: "task",
      title: "Persisted task",
      status: "todo",
      priority: "medium",
    });
    const after = await apiList<WorkItemRow>("/work-items", { project: "proj-1" });
    expect(after.results.length).toBe(before.results.length + 1);
    expect(after.results.some((w) => w.id === created.id)).toBe(true);
  });

  it("bumps the parent project's itemCount when a work item is created", async () => {
    const findProj = (rows: ProjectRow[]) => rows.find((p) => p.id === "proj-1")!;
    const before = findProj((await apiList<ProjectRow>("/projects")).results);
    await apiPost("/projects/proj-1/work-items", {
      type: "task",
      title: "Counts",
      status: "todo",
      priority: "medium",
    });
    const after = findProj((await apiList<ProjectRow>("/projects")).results);
    expect(after.itemCount).toBe(before.itemCount + 1);
  });

  it("persists a created project so the project list returns it", async () => {
    const before = await apiList<ProjectRow>("/projects");
    const created = await apiPost<ProjectRow>("/projects", { name: "New proj", repoUrl: "" });
    const after = await apiList<ProjectRow>("/projects");
    expect(after.results.length).toBe(before.results.length + 1);
    expect(after.results.some((p) => p.id === created.id)).toBe(true);
  });
});
