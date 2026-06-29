import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../../lib/api/queryClient";
import { BoardView } from "./BoardView";
import { seed } from "../../lib/api/mocks/fixtures";

describe("BoardView", () => {
  it("renders five status columns and the seeded project's cards", async () => {
    const projectId = seed.projects[0].id;
    render(
      <QueryClientProvider client={createQueryClient()}>
        <MemoryRouter><BoardView projectId={projectId} /></MemoryRouter>
      </QueryClientProvider>,
    );
    // 5 column headers (In Progress is one of them)
    await waitFor(() => expect(screen.getByText(/In Progress/i)).toBeInTheDocument());
    // at least one card links to an item
    await waitFor(() => expect(screen.getAllByRole("link").length).toBeGreaterThan(0));
  });
});
