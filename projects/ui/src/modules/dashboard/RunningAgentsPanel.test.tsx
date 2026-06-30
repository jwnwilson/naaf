import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../../lib/api/queryClient";
import { RunningAgentsPanel } from "./RunningAgentsPanel";

describe("RunningAgentsPanel", () => {
  it("renders agent rows from the mock", async () => {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RunningAgentsPanel />
      </QueryClientProvider>,
    );
    await waitFor(() =>
      expect(screen.getAllByRole("button").length).toBeGreaterThan(0),
    );
  });

  it("shows the panel header", async () => {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RunningAgentsPanel />
      </QueryClientProvider>,
    );
    await waitFor(() =>
      expect(screen.getByText(/Running Agents/i)).toBeInTheDocument(),
    );
  });

  it("renders a Pause button for running agents", async () => {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RunningAgentsPanel />
      </QueryClientProvider>,
    );
    // seed has 1 running agent
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /pause/i })).toBeInTheDocument(),
    );
  });

  it("renders Assign buttons for non-running agents", async () => {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RunningAgentsPanel />
      </QueryClientProvider>,
    );
    // seed has 2 non-running agents (idle + paused)
    await waitFor(() =>
      expect(screen.getAllByRole("button", { name: /assign/i }).length).toBeGreaterThan(0),
    );
  });

  it("shows active agent count in header", async () => {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RunningAgentsPanel />
      </QueryClientProvider>,
    );
    // seed.agents has 1 running agent
    await waitFor(() =>
      expect(screen.getByText(/1 active/i)).toBeInTheDocument(),
    );
  });
});
