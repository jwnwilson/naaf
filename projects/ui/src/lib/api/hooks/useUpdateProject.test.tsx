import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import { server } from "../mocks/server";
import { useUpdateProject } from "./useUpdateProject";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

test("patches a project and resolves with the updated project", async () => {
  server.use(
    http.patch("/api/projects/p1", async ({ request }) => {
      const body = (await request.json()) as { description?: string };
      return HttpResponse.json({
        success: true, error: null,
        data: { id: "p1", name: "P", description: body.description ?? "", repoUrl: "", itemCount: 0, createdAt: "", updatedAt: "" },
      });
    }),
  );
  const { result } = renderHook(() => useUpdateProject("p1"), { wrapper });
  await act(async () => {
    await result.current.mutateAsync({ description: "new desc" });
  });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.description).toBe("new desc");
});
