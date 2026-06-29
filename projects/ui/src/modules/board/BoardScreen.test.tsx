import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../../lib/api/queryClient";
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
    await waitFor(() => expect(screen.getAllByRole("link").length).toBeGreaterThan(0));
  });
});
