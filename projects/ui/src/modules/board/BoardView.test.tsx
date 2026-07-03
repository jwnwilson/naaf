import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { createQueryClient } from "../../lib/api/queryClient";
import { CreateModalProvider } from "../create/CreateModalProvider";
import { BoardView } from "./BoardView";
import { seed } from "../../lib/api/mocks/fixtures";
import { server } from "../../lib/api/mocks/server";

function renderBoardView(projectId: string) {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <CreateModalProvider>
          <BoardView projectId={projectId} />
        </CreateModalProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("BoardView", () => {
  it("renders five status columns and the seeded project's cards", async () => {
    renderBoardView(seed.projects[0].id);
    await waitFor(() => expect(screen.getByText(/In Progress/i)).toBeInTheDocument());
    await waitFor(() => expect(screen.getAllByRole("link").length).toBeGreaterThan(0));
  });

  it("column + opens Create Work Item", async () => {
    renderBoardView(seed.projects[0].id);
    await waitFor(() => expect(screen.getByText(/In Progress/i)).toBeInTheDocument());
    await userEvent.click(screen.getAllByRole("button", { name: /add .* item/i })[0]);
    expect(await screen.findByRole("dialog")).toHaveTextContent("Create Work Item");
  });

  it("empty-state CTA opens Create Work Item", async () => {
    server.use(
      http.get("/api/work-items", () =>
        HttpResponse.json({ success: true, error: null, data: [], meta: { total: 0, page_size: 50, page_number: 1 } }),
      ),
    );
    renderBoardView("empty-project");
    await userEvent.click(await screen.findByRole("button", { name: /create your first item/i }));
    expect(await screen.findByRole("dialog")).toHaveTextContent("Create Work Item");
  });
});
