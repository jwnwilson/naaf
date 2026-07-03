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
    // seed thread wi-task-3: title rendered by NotificationItem
    await waitFor(() =>
      expect(
        screen.getAllByText("Implement Docker sandbox container").length,
      ).toBeGreaterThan(0),
    );
  });
  it("inbox auto-selects first thread and shows its messages", async () => {
    // Regression guard: thread.id must equal workItemId so useThreadMessages
    // fetches the right messages (thread-1 / thread-2 IDs caused zero messages).
    await renderAt("/inbox");
    // First thread (wi-task-3) is auto-selected; ConversationPane loads its messages.
    // msg-2 is a text message from that thread.
    await waitFor(() =>
      expect(
        screen.getAllByText("I'll start by analysing the existing architecture and then implement the sandbox.").length,
      ).toBeGreaterThan(0),
    );
  });
  it("renders settings", async () => {
    await renderAt("/settings/agents");
    await waitFor(() => expect(screen.getAllByRole("switch").length).toBeGreaterThan(0));
  });
});
