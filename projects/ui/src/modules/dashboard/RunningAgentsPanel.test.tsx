import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../../lib/api/queryClient";
import { RunningAgentsPanel } from "./RunningAgentsPanel";

function renderPanel() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RunningAgentsPanel />
    </QueryClientProvider>,
  );
}

describe("RunningAgentsPanel", () => {
  it("shows the panel header", async () => {
    renderPanel();
    await waitFor(() =>
      expect(screen.getByText(/Running Agents/i)).toBeInTheDocument(),
    );
  });

  it("renders a running role with its work item and an idle role", async () => {
    renderPanel();
    await waitFor(() => expect(screen.getByText("lead")).toBeInTheDocument());
    expect(screen.getByText("wi-task-3")).toBeInTheDocument(); // running lead's work item
    expect(screen.getByText("backend")).toBeInTheDocument();   // idle row
  });

  it("shows the active (running) count in the header", async () => {
    renderPanel();
    await waitFor(() => expect(screen.getByText(/1 active/)).toBeInTheDocument());
  });
});
