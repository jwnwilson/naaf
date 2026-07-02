import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../../lib/api/queryClient";
import { server } from "../../lib/api/mocks/server";
import { routes } from "../../app/routes";

describe("InboxScreen", () => {
  it("renders the thread list and a conversation pane", async () => {
    const router = createMemoryRouter(routes, { initialEntries: ["/inbox"] });
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );
    // seed thread-1: agentId "agent-1" — NotificationItem renders it as title
    // (getAllByText: ChatPanel sidebar also renders the same agentId)
    await waitFor(() => expect(screen.getAllByText("agent-1").length).toBeGreaterThan(0));
  });

  it("shows 'No conversations' when threads list is empty", async () => {
    server.use(
      http.get("/api/threads", () =>
        HttpResponse.json({ success: true, data: [], error: null, meta: null }),
      ),
    );
    const router = createMemoryRouter(routes, { initialEntries: ["/inbox"] });
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );
    await waitFor(() =>
      expect(screen.getByText("No conversations")).toBeInTheDocument(),
    );
  });
});
