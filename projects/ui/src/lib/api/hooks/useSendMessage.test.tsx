import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";
import { server } from "../mocks/server";
import { useSendMessage } from "./useSendMessage";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

test("sends a message and resolves with the created message", async () => {
  server.use(
    http.post("/api/threads/r1/messages", async ({ request }) => {
      const body = (await request.json()) as { content: string };
      return HttpResponse.json(
        {
          success: true,
          error: null,
          data: {
            id: "m1",
            threadId: "r1",
            authorKind: "user",
            authorRole: null,
            model: null,
            kind: "text",
            content: body.content,
            mentions: [],
            payload: null,
            runId: null,
            createdAt: "2026-07-02T00:00:00Z",
          },
        },
        { status: 201 },
      );
    }),
  );

  const { result } = renderHook(() => useSendMessage("r1"), { wrapper });
  await act(async () => {
    await result.current.mutateAsync({ content: "hello" });
  });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.content).toBe("hello");
});
