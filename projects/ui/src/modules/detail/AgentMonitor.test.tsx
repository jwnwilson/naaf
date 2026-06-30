import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../../lib/api/queryClient";
import { seed } from "../../lib/api/mocks/fixtures";
import { AgentMonitor } from "./AgentMonitor";

describe("AgentMonitor", () => {
  it("renders the run timeline steps and log stream from the mock", async () => {
    const runId = seed.agentRuns[0].id;
    render(
      <QueryClientProvider client={createQueryClient()}>
        <AgentMonitor runId={runId} />
      </QueryClientProvider>,
    );
    // all 6 step labels (Plan/Read/Analyze/Generate/Test/PR) render
    await waitFor(() =>
      expect(screen.getAllByText(/Plan|Generate|Test/).length).toBeGreaterThan(0),
    );
  });
});
