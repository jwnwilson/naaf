// src/lib/hooks/useCurrentProjectId.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import { server } from "../api/mocks/server";
import { useCurrentProjectId } from "./useCurrentProjectId";

function wrapper(initialEntries: string[]) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return (
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

test("prefers the ?project= search param", async () => {
  server.use(
    http.get("/api/projects", () =>
      HttpResponse.json({ success: true, error: null, data: [{ id: "p1", name: "A", repoUrl: "", itemCount: 0, createdAt: "x", updatedAt: "x" }], meta: { total: 1, page_size: 50, page_number: 1 } }),
    ),
  );
  const { result } = renderHook(() => useCurrentProjectId(), { wrapper: wrapper(["/projects?project=pX"]) });
  await waitFor(() => expect(result.current).toBe("pX"));
});

test("falls back to the first project", async () => {
  server.use(
    http.get("/api/projects", () =>
      HttpResponse.json({ success: true, error: null, data: [{ id: "p1", name: "A", repoUrl: "", itemCount: 0, createdAt: "x", updatedAt: "x" }], meta: { total: 1, page_size: 50, page_number: 1 } }),
    ),
  );
  const { result } = renderHook(() => useCurrentProjectId(), { wrapper: wrapper(["/projects"]) });
  await waitFor(() => expect(result.current).toBe("p1"));
});
