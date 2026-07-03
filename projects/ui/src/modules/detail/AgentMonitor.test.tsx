import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { expect, test, vi } from "vitest";
import { server } from "../../lib/api/mocks/server";
import { AgentMonitor } from "./AgentMonitor";

function renderMonitor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AgentMonitor runId="r1" />
    </QueryClientProvider>,
  );
}

const RUN = {
  id: "r1",
  workItemId: "w1",
  projectId: "p1",
  autonomyLevel: "gated_all",
  status: "awaiting_gate",
  currentStage: "plan",
  stages: [
    {
      stage: "plan",
      status: "gated",
      role: "lead",
      startedAt: "2026-07-02T00:00:00Z",
      endedAt: null,
    },
  ],
  pendingGate: { kind: "plan", stage: "plan" },
  createdAt: "2026-07-02T00:00:00Z",
  updatedAt: "2026-07-02T00:00:00Z",
  startedAt: "2026-07-02T00:00:00Z",
  endedAt: null,
  tokenUsage: 1050,
  cost: 0.0032,
};

test("shows a View PR link pointing at the run's prUrl when set", async () => {
  const withPr = { ...RUN, status: "succeeded", pendingGate: null, prUrl: "https://github.com/acme/app/pull/42" };
  server.use(
    http.get("/api/runs/r1", () => HttpResponse.json({ success: true, error: null, data: withPr })),
    http.get("/api/runs/r1/events", () => HttpResponse.json({ success: true, error: null, data: [] })),
  );
  renderMonitor();
  const link = await screen.findByRole("link", { name: /view pr/i });
  expect(link).toHaveAttribute("href", "https://github.com/acme/app/pull/42");
});

test("hides the View PR link when the run has no prUrl", async () => {
  server.use(
    http.get("/api/runs/r1", () => HttpResponse.json({ success: true, error: null, data: RUN })),
    http.get("/api/runs/r1/events", () => HttpResponse.json({ success: true, error: null, data: [] })),
  );
  renderMonitor();
  await screen.findByText(/awaiting_gate/);
  expect(screen.queryByRole("link", { name: /view pr/i })).not.toBeInTheDocument();
});

test("renders status + token usage and resolves a pending gate", async () => {
  const gate = vi.fn();
  server.use(
    http.get("/api/runs/r1", () =>
      HttpResponse.json({ success: true, error: null, data: RUN }),
    ),
    http.get("/api/runs/r1/events", () =>
      HttpResponse.json({ success: true, error: null, data: [] }),
    ),
    http.post("/api/runs/r1/gate", async ({ request }) => {
      gate((await request.json() as { decision: string }).decision);
      return HttpResponse.json({ success: true, error: null, data: RUN });
    }),
  );
  renderMonitor();
  expect(await screen.findByText(/awaiting_gate/)).toBeInTheDocument();
  expect(screen.getByText(/1050|1\.0k|1\.1k/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /approve/i }));
  expect(gate).toHaveBeenCalledWith("approve");
});
