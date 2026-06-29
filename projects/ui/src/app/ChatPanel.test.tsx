import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { createQueryClient } from "../lib/api/queryClient";
import { ChatPanel } from "./ChatPanel";

function renderPanel() {
  render(
    <QueryClientProvider client={createQueryClient()}><ChatPanel /></QueryClientProvider>,
  );
}

describe("ChatPanel", () => {
  beforeEach(() => localStorage.clear());
  it("collapses and re-expands, persisting the state", async () => {
    renderPanel();
    // open by default: the collapse control is present
    const collapse = await screen.findByRole("button", { name: /collapse/i });
    await userEvent.click(collapse);
    // collapsed strip shows the CHAT label and an expand control
    await waitFor(() => expect(screen.getByRole("button", { name: /expand|chat/i })).toBeInTheDocument());
    expect(JSON.parse(localStorage.getItem("naaf.chat.open")!)).toBe(false);
  });
});
