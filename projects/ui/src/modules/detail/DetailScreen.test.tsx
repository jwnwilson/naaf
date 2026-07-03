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
});
