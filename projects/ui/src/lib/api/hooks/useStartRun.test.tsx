import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import { server } from "../mocks/server";
import { useStartRun } from "./useStartRun";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

test("starts a run for the work item and resolves with the queued run", async () => {
  server.use(
    http.post("/api/work-items/w1/runs", () =>
      HttpResponse.json(
        { success: true, error: null, data: { id: "r1", workItemId: "w1", projectId: "p1", autonomyLevel: "gated_all", status: "queued", currentStage: null, stages: [], createdAt: "2026-07-03T00:00:00Z", updatedAt: "2026-07-03T00:00:00Z", startedAt: null, tokenUsage: 0, cost: 0, prUrl: null } },
        { status: 201 },
      ),
    ),
  );
  const { result } = renderHook(() => useStartRun("w1", "p1"), { wrapper });
  await act(async () => {
    await result.current.mutateAsync();
  });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.id).toBe("r1");
  expect(result.current.data?.status).toBe("queued");
});
