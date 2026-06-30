import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../lib/api/queryClient";
import { routes } from "./routes";

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

describe("routing", () => {
  it("renders the board screen at /projects", async () => {
    renderAt("/projects?view=board");
    await waitFor(() => expect(screen.getByText(/In Progress/i)).toBeInTheDocument());
  });
  it("renders the dashboard at /dashboard", async () => {
    renderAt("/dashboard");
    await waitFor(() => expect(screen.getByRole("heading", { name: /dashboard/i })).toBeInTheDocument());
  });
  it("renders the inbox at /inbox", async () => {
    renderAt("/inbox");
    await waitFor(() => expect(screen.getByRole("heading", { name: /inbox/i })).toBeInTheDocument());
  });
});
