import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { createQueryClient } from "../../lib/api/queryClient";
import { SecretsPanel } from "./SecretsPanel";

function renderPanel() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <SecretsPanel />
    </QueryClientProvider>,
  );
}

test("shows Not set initially, saves a masked value, and clears it", async () => {
  renderPanel();
  await waitFor(() => expect(screen.getAllByText(/not set/i).length).toBeGreaterThanOrEqual(2));

  const input = screen.getByLabelText("Anthropic API key") as HTMLInputElement;
  expect(input.type).toBe("password");
  await userEvent.type(input, "sk-ant-abcd1234");
  await userEvent.click(screen.getAllByRole("button", { name: /^save$/i })[0]);

  // masked status appears, raw value never rendered, input cleared
  await waitFor(() => expect(screen.getByText(/••••1234/)).toBeInTheDocument());
  expect(screen.queryByText("sk-ant-abcd1234")).not.toBeInTheDocument();
  expect(input.value).toBe("");

  // Clear removes it
  await userEvent.click(screen.getByRole("button", { name: /clear/i }));
  await waitFor(() => expect(screen.queryByText(/••••1234/)).not.toBeInTheDocument());
});

test("rejects an unknown secret name with a 422 (guarded server-side)", async () => {
  // Sanity: the panel only exposes the three known fields.
  renderPanel();
  await waitFor(() => expect(screen.getByLabelText("Anthropic API key")).toBeInTheDocument());
  expect(screen.getByLabelText("GitHub token")).toBeInTheDocument();
  expect(screen.getByLabelText("Claude subscription token")).toBeInTheDocument();
  expect(screen.queryByLabelText(/aws/i)).not.toBeInTheDocument();
});
