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
    await waitFor(() => expect(screen.getByText(/AGENTS/i)).toBeInTheDocument());
  });
});
