import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ActivityFeed } from "./ActivityFeed";
import * as hook from "../../lib/api/hooks/useAgentActivity";

describe("ActivityFeed", () => {
  it("shows typing indicator while working with no content", () => {
    vi.spyOn(hook, "useAgentActivity").mockReturnValue({
      events: [], isWorking: true, textBlocks: [], toolCalls: [], done: false,
    } as never);
    render(<ActivityFeed scope={{ threadId: "w1" }} />);
    expect(screen.getByTestId("activity-typing")).toBeInTheDocument();
  });

  it("renders streamed text and tool lines", () => {
    vi.spyOn(hook, "useAgentActivity").mockReturnValue({
      events: [], isWorking: true, textBlocks: ["Planning…"],
      toolCalls: [{ name: "create_task", result: "ok" }], done: false,
    } as never);
    render(<ActivityFeed scope={{ threadId: "w1" }} />);
    expect(screen.getByText("Planning…")).toBeInTheDocument();
    expect(screen.getByText(/create_task/)).toBeInTheDocument();
  });

  it("renders nothing when idle/done", () => {
    vi.spyOn(hook, "useAgentActivity").mockReturnValue({
      events: [], isWorking: false, textBlocks: [], toolCalls: [], done: true,
    } as never);
    const { container } = render(<ActivityFeed scope={{ threadId: "w1" }} />);
    expect(container).toBeEmptyDOMElement();
  });
});
