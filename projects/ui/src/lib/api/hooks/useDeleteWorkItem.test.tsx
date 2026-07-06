import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import { server } from "../mocks/server";
import { useDeleteWorkItem } from "./useDeleteWorkItem";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

test("deletes a work item and resolves", async () => {
  server.use(
    http.delete("/api/work-items/w1", () =>
      HttpResponse.json({ success: true, error: null, data: null }),
    ),
  );
  const { result } = renderHook(() => useDeleteWorkItem("w1", "p1"), { wrapper });
  await act(async () => {
    await result.current.mutateAsync();
  });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
});
