import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../../lib/api/queryClient";
import { routes } from "../../app/routes";

describe("SettingsScreen", () => {
  it("renders the agent settings with toggles from the mock", async () => {
    const router = createMemoryRouter(routes, { initialEntries: ["/settings/agents"] });
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getAllByRole("switch").length).toBeGreaterThan(0));
  });
});
