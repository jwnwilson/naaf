import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
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

  it("marks the chosen option resolved", () => {
    render(
      <MessageItem
        message={msg({
          kind: "question",
          content: "Plan gate",
          payload: {
            options: [
              { id: "approve", label: "Approve" },
              { id: "reject", label: "Reject" },
            ],
            resolved_option: "approve",
          },
        })}
      />,
    );
    const approve = screen.getByRole("button", { name: /Approve/ });
    expect(approve).toBeDisabled();
    expect(screen.getByRole("button", { name: /Reject/ })).toBeDisabled();
  });

  it("calls onAnswer when an option is clicked", () => {
    const onAnswer = vi.fn();
    render(
      <MessageItem
        message={msg({
          id: "q1",
          kind: "question",
          payload: {
            options: [
              { id: "approve", label: "Approve" },
              { id: "reject", label: "Reject" },
            ],
            resolved_option: null,
          },
        })}
        onAnswer={onAnswer}
      />,
    );
    screen.getByRole("button", { name: /Approve/ }).click();
    expect(onAnswer).toHaveBeenCalledWith("q1", "approve");
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
