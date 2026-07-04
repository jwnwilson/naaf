import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import { server } from "../mocks/server";
import { useAgents, AGENTS_POLL_MS } from "./useAgents";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

test("fetches role-oriented live agents", async () => {
  server.use(
    http.get("/api/agents", () =>
      HttpResponse.json({
        success: true,
        error: null,
        data: [
          { role: "lead", model: "opus", status: "running", runId: "r1",
            workItemId: "wi1", currentStage: "plan", progress: 0.5, tokenUsage: 1200 },
          { role: "backend", model: "sonnet", status: "idle", runId: null,
            workItemId: null, currentStage: null, progress: null, tokenUsage: 0 },
        ],
      }),
    ),
  );
  const { result } = renderHook(() => useAgents(), { wrapper });
  await waitFor(() => expect(result.current.data).toHaveLength(2));
  expect(result.current.data?.[0].role).toBe("lead");
  expect(result.current.data?.[0].status).toBe("running");
});

test("exposes a poll interval", () => {
  expect(AGENTS_POLL_MS).toBe(5000);
});
