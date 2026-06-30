import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../../lib/api/queryClient";
import { ConversationPane } from "./ConversationPane";
import { seed } from "../../lib/api/mocks/fixtures";

describe("ConversationPane", () => {
  it("renders the conversation header and messages for the selected item", async () => {
    const item = seed.inboxItems[0];
    render(
      <QueryClientProvider client={createQueryClient()}>
        <ConversationPane item={item} />
      </QueryClientProvider>,
    );
    // the item id appears in the header
    await waitFor(() => expect(screen.getByText(new RegExp(item.workItemId))).toBeInTheDocument());
  });

  it("renders at least one message bubble for the selected item (not the empty state)", async () => {
    // inbox-1 conversationId must resolve to a thread that has seeded messages
    const item = seed.inboxItems[0];
    render(
      <QueryClientProvider client={createQueryClient()}>
        <ConversationPane item={item} />
      </QueryClientProvider>,
    );
    // "No messages yet" must NOT appear — real message content must render
    await waitFor(() =>
      expect(screen.queryByText(/No messages yet/i)).not.toBeInTheDocument(),
    );
    // At least one seeded message bubble content is visible
    await waitFor(() =>
      expect(
        screen.getByText(/Please implement the Docker sandbox container/i),
      ).toBeInTheDocument(),
    );
  });
});
