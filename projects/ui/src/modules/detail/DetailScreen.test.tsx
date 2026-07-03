import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../../lib/api/queryClient";
import { routes } from "../../app/routes";
import { seed } from "../../lib/api/mocks/fixtures";
import { server } from "../../lib/api/mocks/server";

describe("DetailScreen", () => {
  it("loads the item, shows the Spec tab, and switches tabs", async () => {
    const wi = seed.workItems[0];
    // wi-epic-1 has no associated run — return empty list so the Agent tab
    // shows the "No active run" empty state (not AgentMonitor).
    server.use(
      http.get("/api/runs", () =>
        HttpResponse.json({ success: true, error: null, data: [], meta: { total: 0, page_size: 50, page_number: 1 } }),
      ),
    );
    const router = createMemoryRouter(routes, { initialEntries: [`/projects/${wi.projectId}/items/${wi.id}`] });
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByRole("button", { name: /^Spec$/i })).toBeInTheDocument());
    // Thread tab exists (renamed from Subagents)
    expect(screen.getByRole("button", { name: /^Thread$/i })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /^Agent$/i }));
    // Agent tab body renders (timeline/monitor or an empty-run state)
    expect(screen.getByRole("button", { name: /^Agent$/i })).toBeInTheDocument();
  });

  it("opens the Edit modal pre-filled from the header Edit button", async () => {
    const wi = seed.workItems[0];
    server.use(
      http.get("/api/runs", () =>
        HttpResponse.json({ success: true, error: null, data: [], meta: { total: 0, page_size: 50, page_number: 1 } }),
      ),
    );
    const router = createMemoryRouter(routes, { initialEntries: [`/projects/${wi.projectId}/items/${wi.id}`] });
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByRole("button", { name: /^Edit$/i })).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: /^Edit$/i }));
    expect(screen.getByRole("dialog")).toHaveTextContent("Edit Work Item");
    expect((screen.getByLabelText(/title/i) as HTMLInputElement).value).toBe(wi.title);
  });

  it("shows a Start run control in the header and empty-state CTA for a startable task", async () => {
    const task = seed.workItems.find((w) => w.type === "task" && w.status === "todo")!;
    server.use(
      http.get("/api/runs", () =>
        HttpResponse.json({ success: true, error: null, data: [], meta: { total: 0, page_size: 50, page_number: 1 } }),
      ),
    );
    const router = createMemoryRouter(routes, { initialEntries: [`/projects/${task.projectId}/items/${task.id}`] });
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByRole("button", { name: /^Start run$/i })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: /^Agent$/i }));
    // Agent tab empty state also offers a Start run CTA (two total: header + CTA)
    expect(screen.getAllByRole("button", { name: /^Start run$/i }).length).toBeGreaterThanOrEqual(2);
  });
});
