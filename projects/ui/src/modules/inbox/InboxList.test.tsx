import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../../lib/api/queryClient";
import { InboxList } from "./InboxList";

describe("InboxList", () => {
  it("renders thread rows from the seeded threads data", async () => {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <InboxList onSelect={() => {}} />
      </QueryClientProvider>,
    );
    // seed.threads[0]: title "Implement Docker sandbox container"
    await waitFor(() =>
      expect(screen.getByText("Implement Docker sandbox container")).toBeInTheDocument(),
    );
  });
});
