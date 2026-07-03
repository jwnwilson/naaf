import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import { server } from "../mocks/server";
import { useCreateProject } from "./useCreateProject";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

test("posts a project and resolves with the created project", async () => {
  server.use(
    http.post("/api/projects", async ({ request }) => {
      const body = (await request.json()) as { name: string; repoUrl: string };
      return HttpResponse.json(
        { success: true, error: null, data: { id: "p9", name: body.name, repoUrl: body.repoUrl, itemCount: 0, createdAt: "2026-07-03T00:00:00Z", updatedAt: "2026-07-03T00:00:00Z" } },
        { status: 201 },
      );
    }),
  );
  const { result } = renderHook(() => useCreateProject(), { wrapper });
  await act(async () => {
    await result.current.mutateAsync({ name: "New", repoUrl: "" });
  });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.id).toBe("p9");
});
