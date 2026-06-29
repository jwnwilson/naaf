import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../../lib/api/queryClient";
import { LiveAgentsRibbon } from "./LiveAgentsRibbon";

describe("LiveAgentsRibbon", () => {
  it("renders the LIVE AGENTS label and agent chips from the mock", async () => {
    render(
      <QueryClientProvider client={createQueryClient()}><LiveAgentsRibbon /></QueryClientProvider>,
    );
    expect(screen.getByText(/LIVE AGENTS/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText(/RUN|IDLE/).length).toBeGreaterThan(0));
  });
});
