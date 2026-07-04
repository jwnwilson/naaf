import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import { server } from "../mocks/server";
import { useBoard } from "./useBoard";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

test("refetches the board on the poll interval so agent-created items appear", async () => {
  let hits = 0;
  server.use(
    http.get("/api/projects/p1/board", () => {
      hits += 1;
      return HttpResponse.json({ success: true, data: [], error: null, meta: null });
    }),
  );
  // Tiny interval keeps the test fast and non-flaky.
  const { result } = renderHook(() => useBoard("p1", 20), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  const firstHits = hits;
  await waitFor(() => expect(hits).toBeGreaterThan(firstHits), { timeout: 1000 });
});

test("does not fetch when there is no project id", async () => {
  let hits = 0;
  server.use(
    http.get("/api/projects//board", () => {
      hits += 1;
      return HttpResponse.json({ success: true, data: [], error: null, meta: null });
    }),
  );
  renderHook(() => useBoard("", 20), { wrapper });
  await new Promise((r) => setTimeout(r, 60));
  expect(hits).toBe(0);
});
