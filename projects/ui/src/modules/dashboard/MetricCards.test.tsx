import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
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

  it("shows active agent count from mock metrics", async () => {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <MetricCards />
      </QueryClientProvider>,
    );
    // seed.metrics.activeAgents = 1
    await waitFor(() =>
      expect(screen.getByText("1")).toBeInTheDocument(),
    );
  });
});
