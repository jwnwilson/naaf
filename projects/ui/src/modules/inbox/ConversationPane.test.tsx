import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../../lib/api/mocks/server";
import { createQueryClient } from "../../lib/api/queryClient";
import type { Message } from "../../lib/api/hooks";
import { ConversationPane } from "./ConversationPane";

function renderPane(threadId: string) {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <ConversationPane threadId={threadId} />
    </QueryClientProvider>,
  );
}

function makeMsg(overrides: Partial<Message> = {}): Message {
  return {
    id: "m0",
    threadId: "r1",
    authorKind: "agent",
    authorRole: "engineer",
    model: null,
    kind: "text",
    content: "existing message",
    mentions: [],
    payload: null,
    runId: null,
    createdAt: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("ConversationPane", () => {
  it("renders thread messages", async () => {
    server.use(
      http.get("/api/threads/r1/messages", () =>
        HttpResponse.json({
          success: true,
          data: [makeMsg()],
          error: null,
          meta: null,
        }),
      ),
    );
    renderPane("r1");
    expect(await screen.findByText("existing message")).toBeInTheDocument();
  });

  it("sends a reply and it stays visible after refetch", async () => {
    const stored: Message[] = [];
    server.use(
      http.get("/api/threads/r1/messages", () =>
        HttpResponse.json({ success: true, data: stored, error: null, meta: null }),
      ),
      http.post("/api/threads/r1/messages", async ({ request }) => {
        const body = (await request.json()) as { content: string };
        const msg = makeMsg({ id: "m1", authorKind: "user", content: body.content });
        stored.push(msg);
        return HttpResponse.json(
          { success: true, data: msg, error: null, meta: null },
          { status: 201 },
        );
      }),
    );
    renderPane("r1");
    await userEvent.type(screen.getByPlaceholderText("Reply…"), "looks good");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));
    expect(await screen.findByText("looks good")).toBeInTheDocument();
  });
});
