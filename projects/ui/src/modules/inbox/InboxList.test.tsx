import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../../lib/api/queryClient";
import { InboxList } from "./InboxList";

describe("InboxList", () => {
  it("renders the filter tabs and the seeded notifications", async () => {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <InboxList onSelect={() => {}} />
      </QueryClientProvider>,
    );
    expect(screen.getByText("Action needed")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText(/ACTION NEEDED|INFO|RESOLVED|REVIEW NEEDED/).length).toBeGreaterThan(0));
  });
});
