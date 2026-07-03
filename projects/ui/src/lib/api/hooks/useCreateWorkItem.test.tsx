import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import { server } from "../mocks/server";
import { useCreateWorkItem } from "./useCreateWorkItem";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

test("posts a work item under the project and resolves with it", async () => {
  server.use(
    http.post("/api/projects/p1/work-items", async ({ request }) => {
      const body = (await request.json()) as { type: string; title: string };
      return HttpResponse.json(
        { success: true, error: null, data: { id: "w9", type: body.type, title: body.title, status: "todo", priority: "medium", projectId: "p1", createdAt: "2026-07-03T00:00:00Z", updatedAt: "2026-07-03T00:00:00Z" } },
        { status: 201 },
      );
    }),
  );
  const { result } = renderHook(() => useCreateWorkItem("p1"), { wrapper });
  await act(async () => {
    await result.current.mutateAsync({ type: "epic", title: "E", status: "todo", priority: "medium" });
  });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.id).toBe("w9");
});
