import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { server } from "../../lib/api/mocks/server";
import { createQueryClient } from "../../lib/api/queryClient";
import type { Message } from "../../lib/api/hooks";
import { ConversationPane } from "./ConversationPane";

function renderPane(threadId: string) {
  render(
    <MemoryRouter>
      <QueryClientProvider client={createQueryClient()}>
        <ConversationPane threadId={threadId} />
      </QueryClientProvider>
    </MemoryRouter>,
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

  it("links the work-item title to its detail screen", async () => {
    server.use(
      http.get("/api/threads/wi-task-3", () =>
        HttpResponse.json({
          success: true,
          data: {
            id: "wi-task-3",
            workItemId: "wi-task-3",
            projectId: "proj-1",
            title: "Implement Docker sandbox container",
            status: "in_progress",
            lastMessage: null,
            messageCount: 0,
            participants: [],
            createdAt: "2026-06-29T13:00:00Z",
            filesWritten: [],
            participantDetails: [],
          },
          error: null,
          meta: null,
        }),
      ),
      http.get("/api/threads/wi-task-3/messages", () =>
        HttpResponse.json({ success: true, data: [], error: null, meta: null }),
      ),
    );
    renderPane("wi-task-3");
    const link = await screen.findByRole("link", {
      name: /Implement Docker sandbox container/,
    });
    expect(link).toHaveAttribute("href", "/projects/proj-1/items/wi-task-3");
  });

  it("links a project-level thread to its board", async () => {
    server.use(
      http.get("/api/threads/project:proj-1", () =>
        HttpResponse.json({
          success: true,
          data: {
            id: "project:proj-1",
            workItemId: "",
            projectId: "proj-1",
            title: "Design review",
            status: "in_progress",
            lastMessage: null,
            messageCount: 0,
            participants: [],
            createdAt: "2026-06-29T13:00:00Z",
            filesWritten: [],
            participantDetails: [],
          },
          error: null,
          meta: null,
        }),
      ),
      http.get("/api/threads/project:proj-1/messages", () =>
        HttpResponse.json({ success: true, data: [], error: null, meta: null }),
      ),
    );
    renderPane("project:proj-1");
    const link = await screen.findByRole("link", { name: /Design review/ });
    expect(link).toHaveAttribute("href", "/projects?project=proj-1");
  });
});
