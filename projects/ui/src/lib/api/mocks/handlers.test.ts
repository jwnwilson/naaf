import { describe, expect, it } from "vitest";
import type { HttpHandler } from "msw";
import { apiFetch, apiList } from "../client";
import { mockOnlyHandlers, liveHandlers } from "./handlers";

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
});

describe("handler split", () => {
  it("keeps the unbacked resources mocked and the live groups separate", () => {
    const path = (h: HttpHandler) => String(h.info.path);
    const live = liveHandlers.map(path).join(" ");
    const mock = mockOnlyHandlers.map(path).join(" ");
    expect(live).toMatch(/\/api\/projects/);
    expect(live).toMatch(/\/api\/work-items/);
    expect(live).toMatch(/\/api\/teams/);
    expect(mock).toMatch(/\/api\/runs|\/api\/dashboard/);
    // board and run endpoints have no backend — always mocked
    expect(mock).toMatch(/\/api\/projects\/:id\/board/);
    expect(mock).toMatch(/\/api\/work-items\/:id\/run/);
    // these endpoints must NOT be in live (board tree and work-item runs are A2-mocked)
    expect(live).not.toMatch(/board/);
    expect(live).not.toMatch(/\/run/);
    // /inbox is retired — must not appear anywhere
    expect(live).not.toMatch(/\/inbox/);
    expect(mock).not.toMatch(/\/inbox/);
    // /threads is now live (backed by Task 5 backend)
    expect(live).toMatch(/\/api\/threads/);
    expect(mock).not.toMatch(/\/api\/threads/);
  });
});
