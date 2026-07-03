import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import { server } from "../mocks/server";
import { useUpdateWorkItem } from "./useUpdateWorkItem";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

test("patches the work item and resolves with the updated item", async () => {
  let capturedBody: Record<string, unknown> = {};
  server.use(
    http.patch("/api/work-items/w1", async ({ request }) => {
      capturedBody = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({
        success: true,
        error: null,
        data: { id: "w1", type: "task", title: capturedBody.title, status: "todo", priority: capturedBody.priority, projectId: "p1", spec: capturedBody.spec, createdAt: "2026-07-03T00:00:00Z", updatedAt: "2026-07-03T00:00:00Z" },
      });
    }),
  );
  const { result } = renderHook(() => useUpdateWorkItem("w1", "p1"), { wrapper });
  await act(async () => {
    await result.current.mutateAsync({ title: "Renamed", priority: "high", spec: "New spec" });
  });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(capturedBody).toEqual({ title: "Renamed", priority: "high", spec: "New spec" });
  expect(result.current.data?.title).toBe("Renamed");
});
