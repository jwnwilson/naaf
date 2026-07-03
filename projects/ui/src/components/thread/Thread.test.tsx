import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Message } from "../../lib/api/hooks";
import { MessageItem } from "./MessageItem";

function msg(overrides: Partial<Message>): Message {
  return {
    id: "m1",
    threadId: "wi-1",
    authorKind: "agent",
    authorRole: "engineer",
    model: null,
    kind: "text",
    content: "hello",
    mentions: [],
    payload: null,
    runId: null,
    createdAt: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("MessageItem", () => {
  it("file_write card shows path", () => {
    render(
      <MessageItem
        message={msg({
          kind: "file_write",
          content: "Wrote file",
          payload: { path: "src/foo.ts", lines: 42 },
        })}
      />,
    );
    expect(screen.getByText("src/foo.ts")).toBeInTheDocument();
  });

  it("question renders option buttons", () => {
    render(
      <MessageItem
        message={msg({
          kind: "question",
          content: "Which approach?",
          payload: {
            options: [
              { id: "a", label: "Option A" },
              { id: "b", label: "Option B" },
            ],
          },
        })}
      />,
    );
    expect(screen.getByRole("button", { name: "Option A" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Option B" })).toBeInTheDocument();
  });

  it("model badge appears for agent messages", () => {
    render(
      <MessageItem
        message={msg({
          authorKind: "agent",
          model: "claude-sonnet-4-6",
          content: "I am an agent.",
        })}
      />,
    );
    expect(screen.getByText("claude-sonnet-4-6")).toBeInTheDocument();
  });
});
