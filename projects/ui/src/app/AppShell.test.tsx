import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

  it("applies the dark base background to the shell root (no white bleed-through)", async () => {
    const router = createMemoryRouter(routes, { initialEntries: ["/projects?view=board"] });
    const { container } = render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );
    const root = container.querySelector("div.flex.h-screen") as HTMLElement;
    expect(root).not.toBeNull();
    expect(root.className).toContain("bg-bg-base");
  });

  it("New button opens the Create Work Item modal when a project exists", async () => {
    const router = createMemoryRouter(routes, { initialEntries: ["/projects?view=board"] });
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );
    // Wait for the board to render (projects data loaded via MSW)
    await waitFor(() => expect(screen.getByText(/In Progress/i)).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: /new/i }));
    expect(await screen.findByRole("dialog")).toHaveTextContent("Create Work Item");
  });
});
