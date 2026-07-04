import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../../lib/api/mocks/server";
import { createQueryClient } from "../../lib/api/queryClient";
import { MetricCards } from "./MetricCards";

describe("MetricCards", () => {
  it("renders metric cards from the mock dashboard", async () => {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <MetricCards />
      </QueryClientProvider>,
    );
    await waitFor(() =>
      expect(screen.getByText(/ACTIVE AGENTS|AGENTS/i)).toBeInTheDocument(),
    );
  });

  it("renders the spend card with accent styling", async () => {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <MetricCards />
      </QueryClientProvider>,
    );
    await waitFor(() =>
      expect(screen.getByText(/SPEND/i)).toBeInTheDocument(),
    );
  });

  it("renders the tokens and projects cards", async () => {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <MetricCards />
      </QueryClientProvider>,
    );
    await waitFor(() => {
      expect(screen.getByText(/TOKENS/i)).toBeInTheDocument();
      expect(screen.getByText(/PROJECTS/i)).toBeInTheDocument();
    });
  });

  it("shows formatted spend value from mock metrics", async () => {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <MetricCards />
      </QueryClientProvider>,
    );
    // seed.metrics.totalSpend = 42.85
    await waitFor(() =>
      expect(screen.getByText("$42.85")).toBeInTheDocument(),
    );
  });

  it("shows the active-agents count from live agents", async () => {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <MetricCards />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByText("ACTIVE AGENTS")).toBeInTheDocument());
    // MSW seed has exactly one running role (lead)
    await waitFor(() => expect(screen.getByText(/1 running now/)).toBeInTheDocument());
  });

  it("sources ACTIVE AGENTS from live agents, not dashboard metrics", async () => {
    server.use(
      http.get("/api/agents", () =>
        HttpResponse.json({
          success: true,
          error: null,
          data: [
            {
              role: "lead",
              model: "opus",
              status: "running",
              runId: "r1",
              workItemId: "wi1",
              currentStage: "plan",
              progress: 0.3,
              tokenUsage: 100,
            },
            {
              role: "backend",
              model: "sonnet",
              status: "running",
              runId: "r2",
              workItemId: "wi2",
              currentStage: "implement",
              progress: 0.5,
              tokenUsage: 200,
            },
            {
              role: "qa",
              model: "haiku",
              status: "idle",
              runId: null,
              workItemId: null,
              currentStage: null,
              progress: null,
              tokenUsage: 0,
            },
          ],
        }),
      ),
    );
    render(
      <QueryClientProvider client={createQueryClient()}>
        <MetricCards />
      </QueryClientProvider>,
    );
    // 2 running roles from /agents — NOT seed.metrics.activeAgents (1)
    await waitFor(() =>
      expect(screen.getByText(/2 running now/)).toBeInTheDocument(),
    );
  });

  it("shows the green running indicator dot when agents are active", async () => {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <MetricCards />
      </QueryClientProvider>,
    );
    // one running role (lead) in MSW seed → dot renders
    await waitFor(() =>
      expect(screen.getByTestId("active-agents-dot")).toBeInTheDocument(),
    );
  });
});
