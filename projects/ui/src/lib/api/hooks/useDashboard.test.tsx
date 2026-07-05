import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import { server } from "../mocks/server";
import { useActivity, useTokenUsage, DASHBOARD_POLL_MS } from "./useDashboard";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

test("exposes a dashboard poll interval", () => {
  expect(DASHBOARD_POLL_MS).toBe(10000);
});

test("useTokenUsage fetches the daily series", async () => {
  server.use(
    http.get("/api/dashboard/token-usage", () =>
      HttpResponse.json({ success: true, error: null,
        data: [{ day: "2026-07-05", tokens: 1200 }] }),
    ),
  );
  const { result } = renderHook(() => useTokenUsage(), { wrapper });
  await waitFor(() => expect(result.current.data).toHaveLength(1));
  expect(result.current.data?.[0].tokens).toBe(1200);
});

test("useActivity fetches recent activity rows", async () => {
  server.use(
    http.get("/api/activity", () =>
      HttpResponse.json({ success: true, error: null,
        data: [{ id: "e1", type: "agent_write", description: "engineer finished implement",
                  agentId: "engineer", workItemId: null, createdAt: "2026-07-05T00:00:00Z" }] }),
    ),
  );
  const { result } = renderHook(() => useActivity(), { wrapper });
  await waitFor(() => expect(result.current.data).toHaveLength(1));
  expect(result.current.data?.[0].type).toBe("agent_write");
});
