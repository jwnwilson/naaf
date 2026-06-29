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
});
