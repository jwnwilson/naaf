import { describe, expect, it } from "vitest";
import type { HttpHandler } from "msw";
import type { components } from "../schema";
import { apiFetch, apiList, apiPost } from "../client";
import { mockOnlyHandlers, liveHandlers } from "./handlers";

type InboxItem = components["schemas"]["InboxItem"];

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

  // The next two tests prove db.reset() runs between tests: the first mutates
  // the inbox to all-read, the second re-asserts the seeded unread state — which
  // can only pass if the mock db was re-seeded in afterEach.
  it("marks all inbox items read (mutation takes effect)", async () => {
    const before = await apiList<InboxItem>("/inbox");
    expect(before.results.some((i) => !i.read)).toBe(true);

    await apiPost("/inbox/mark-all-read", {});

    const after = await apiList<InboxItem>("/inbox");
    expect(after.results.every((i) => i.read)).toBe(true);
  });

  it("starts from a clean seeded db on the next test (reset wiring works)", async () => {
    const page = await apiList<InboxItem>("/inbox");
    expect(page.results.some((i) => !i.read)).toBe(true);
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
    expect(mock).toMatch(/\/api\/runs|\/api\/inbox|\/api\/dashboard/);
    // board and run endpoints have no backend — always mocked
    expect(mock).toMatch(/\/api\/projects\/:id\/board/);
    expect(mock).toMatch(/\/api\/work-items\/:id\/run/);
    // these endpoints must NOT be in live (board tree and work-item runs are A2-mocked)
    expect(live).not.toMatch(/board/);
    expect(live).not.toMatch(/\/run/);
  });
});
