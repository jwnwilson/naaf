import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { NotificationItem } from "./NotificationItem";
import type { components } from "../../lib/api/schema";
type InboxItem = components["schemas"]["InboxItem"];

const item = { id: "n1", type: "action_needed", title: "Approve the PR",
  preview: "The agent finished and opened a PR.", agentId: "agent-1",
  workItemId: "NAAF-1", conversationId: "c1", read: false, createdAt: "" } as InboxItem;

describe("NotificationItem", () => {
  it("renders the badge, title and fires onSelect", async () => {
    const onSelect = vi.fn();
    render(<NotificationItem item={item} selected={false} onSelect={onSelect} />);
    expect(screen.getByText("Approve the PR")).toBeInTheDocument();
    expect(screen.getByText(/ACTION REQUIRED/i)).toBeInTheDocument();
    await userEvent.click(screen.getByText("Approve the PR"));
    expect(onSelect).toHaveBeenCalledWith("n1");
  });
});
