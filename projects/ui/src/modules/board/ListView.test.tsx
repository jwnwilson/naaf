import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../../lib/api/queryClient";
import { ListView } from "./ListView";
import { seed } from "../../lib/api/mocks/fixtures";

describe("ListView", () => {
  it("renders grouped rows for the seeded project", async () => {
    const projectId = seed.projects[0].id;
    render(
      <QueryClientProvider client={createQueryClient()}>
        <MemoryRouter><ListView projectId={projectId} /></MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getAllByRole("link").length).toBeGreaterThan(0));
  });
});
