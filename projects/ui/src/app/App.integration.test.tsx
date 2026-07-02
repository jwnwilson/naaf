import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../lib/api/queryClient";
import { routes } from "./routes";

async function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

describe("app integration", () => {
  it("renders the dashboard", async () => {
    await renderAt("/dashboard");
    await waitFor(() => expect(screen.getByText("Token Usage")).toBeInTheDocument());
  });
  it("renders the board", async () => {
    await renderAt("/projects?view=board");
    await waitFor(() => expect(screen.getByText(/In Progress/i)).toBeInTheDocument());
  });
  it("renders the inbox", async () => {
    await renderAt("/inbox");
    // seed thread-1: agentId "agent-1" rendered by NotificationItem
    await waitFor(() =>
      expect(screen.getAllByText("agent-1").length).toBeGreaterThan(0),
    );
  });
  it("renders settings", async () => {
    await renderAt("/settings/agents");
    await waitFor(() => expect(screen.getAllByRole("switch").length).toBeGreaterThan(0));
  });
});
