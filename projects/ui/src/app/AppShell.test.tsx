import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../lib/api/queryClient";
import { routes } from "./routes";

describe("AppShell", () => {
  it("renders sidebar + topbar + routed screen + chat together", async () => {
    const router = createMemoryRouter(routes, { initialEntries: ["/projects?view=board"] });
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByText(/In Progress/i)).toBeInTheDocument());
    // "Projects" appears in both sidebar nav + topbar title — getAllByText tolerates both
    expect(screen.getAllByText(/Projects/)[0]).toBeInTheDocument();           // sidebar nav
    expect(screen.getByRole("button", { name: /new/i })).toBeInTheDocument(); // topbar
    expect(screen.getByRole("button", { name: /collapse|chat/i })).toBeInTheDocument(); // chat
  });
});
