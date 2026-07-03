import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../../lib/api/queryClient";
import { server } from "../../lib/api/mocks/server";
import { routes } from "../../app/routes";

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

describe("BoardScreen", () => {
  it("shows the board (kanban columns) at view=board", async () => {
    renderAt("/projects?view=board");
    await waitFor(() => expect(screen.getByText(/In Progress/i)).toBeInTheDocument());
  });
  it("shows the list at view=list", async () => {
    renderAt("/projects?view=list");
    // Assert a ListView-specific element: a work-item row link to /items/ —
    // sidebar nav links do not match, so this proves ListView actually rendered rows.
    await waitFor(() => {
      const itemLinks = screen
        .getAllByRole("link")
        .filter((a) => (a as HTMLAnchorElement).getAttribute("href")?.includes("/items/"));
      expect(itemLinks.length).toBeGreaterThan(0);
    });
  });

  it("uses ?project= param instead of falling back to the first project", async () => {
    // proj-2 has a distinctive item "Board Kanban View" that proj-1 does not.
    // Override the work-items handler to return a sentinel item only for proj-2,
    // proving that the board requested project=proj-2 (the second project in the list).
    server.use(
      http.get("/api/work-items", ({ request }) => {
        const url = new URL(request.url);
        const project = url.searchParams.get("project");
        const items = project === "proj-2"
          ? [
              {
                id: "wi-sentinel",
                type: "task",
                title: "Sentinel Task For Proj2",
                status: "todo",
                priority: "medium",
                projectId: "proj-2",
                epicId: null,
                featureId: null,
                tokenUsageThisRun: null,
                tokenUsageAllRuns: null,
                tokenLimit: null,
                spec: null,
                attachments: null,
                createdAt: "2026-07-01T00:00:00Z",
                updatedAt: "2026-07-01T00:00:00Z",
              },
            ]
          : [];
        return HttpResponse.json({
          success: true,
          data: items,
          error: null,
          meta: { total: items.length, page_size: 50, page_number: 1 },
        });
      }),
    );

    // proj-1 is first in the project list; without the fix, the board would use it.
    // With the fix, ?project=proj-2 wins and the sentinel item should appear.
    renderAt("/projects?project=proj-2");
    await waitFor(() =>
      expect(screen.getByText("Sentinel Task For Proj2")).toBeInTheDocument(),
    );
  });
});
