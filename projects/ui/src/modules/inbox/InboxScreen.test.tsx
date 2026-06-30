import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../../lib/api/queryClient";
import { routes } from "../../app/routes";

describe("InboxScreen", () => {
  it("renders the notification list and a conversation", async () => {
    const router = createMemoryRouter(routes, { initialEntries: ["/inbox"] });
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByText("Action needed")).toBeInTheDocument());
    // at least one notification badge renders
    await waitFor(() => expect(screen.getAllByText(/ACTION NEEDED|INFO|RESOLVED|REVIEW NEEDED/).length).toBeGreaterThan(0));
  });
});
