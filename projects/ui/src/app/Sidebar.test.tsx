import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../lib/api/queryClient";
import { Sidebar } from "./Sidebar";

function renderSidebar() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter><Sidebar /></MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Sidebar", () => {
  it("renders nav items and the seeded project list", async () => {
    renderSidebar();
    expect(screen.getByText(/Dashboard/)).toBeInTheDocument();
    expect(screen.getByText(/Projects/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByRole("link").length).toBeGreaterThan(3));
  });

  it("does not render an Agents nav item", () => {
    renderSidebar();
    expect(screen.queryByText("Agents")).not.toBeInTheDocument();
  });

  it("shows the green running indicator dot and active-agent count next to Dashboard", async () => {
    renderSidebar();
    // mock dashboard metrics report activeAgents = 1 (> 0)
    await waitFor(() =>
      expect(screen.getByTestId("dashboard-running-dot")).toBeInTheDocument(),
    );
    const dot = screen.getByTestId("dashboard-running-dot");
    expect(dot.parentElement).toHaveTextContent("1");
  });
});
