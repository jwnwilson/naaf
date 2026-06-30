import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../../lib/api/queryClient";
import { routes } from "../../app/routes";

describe("DashboardScreen", () => {
  it("renders metric cards, the agents panel and the token chart", async () => {
    const router = createMemoryRouter(routes, { initialEntries: ["/dashboard"] });
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );
    // Dashboard-specific content the sidebar can't satisfy: the TokenChart and
    // ActivityFeed headings + a metric-card label only DashboardScreen renders.
    await waitFor(() => expect(screen.getByText("Token Usage")).toBeInTheDocument());
    expect(screen.getByText("Activity")).toBeInTheDocument();
    expect(screen.getByText("TOTAL SPEND")).toBeInTheDocument();
  });
});
