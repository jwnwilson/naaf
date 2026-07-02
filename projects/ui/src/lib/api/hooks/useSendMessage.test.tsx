import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, expect, test } from "vitest";
import { useSendMessage } from "./useSendMessage";

const server = setupServer(
  http.post("/api/threads/r1/messages", async ({ request }) => {
    const body = (await request.json()) as { content: string };
    return HttpResponse.json(
      {
        success: true,
        error: null,
        data: {
          id: "m1",
          conversationId: "r1",
          role: "user",
          agentId: null,
          content: body.content,
          createdAt: "2026-07-02T00:00:00Z",
        },
      },
      { status: 201 },
    );
  }),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

test("sends a message and resolves with the created message", async () => {
  const { result } = renderHook(() => useSendMessage("r1"), { wrapper });
  await act(async () => {
    await result.current.mutateAsync({ content: "hello" });
  });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.content).toBe("hello");
});
