import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import { server } from "../mocks/server";
import { useResolveGate } from "./useResolveGate";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

test("posts a gate decision and resolves", async () => {
  server.use(
    http.post("/api/runs/r1/gate", async ({ request }) => {
      const body = (await request.json()) as { decision: string };
      return HttpResponse.json({ success: true, error: null, data: { id: "r1", decision: body.decision } });
    }),
  );
  const { result } = renderHook(() => useResolveGate("r1"), { wrapper });
  await act(async () => { await result.current.mutateAsync({ decision: "approve" }); });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
});
