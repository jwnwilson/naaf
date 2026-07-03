import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { createQueryClient } from "../../lib/api/queryClient";
import { ThreadComposer } from "./ThreadComposer";

function renderComposer(workItemId = "wi1") {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <ThreadComposer workItemId={workItemId} />
    </QueryClientProvider>,
  );
}

describe("ThreadComposer", () => {
  it("inserts a role mention when a chip is clicked", async () => {
    // Arrange
    renderComposer();

    // Act
    await userEvent.click(screen.getByRole("button", { name: "@backend" }));

    // Assert
    expect(screen.getByPlaceholderText(/reply/i)).toHaveValue("@backend ");
  });

  it("appends mention with a separating space when input already has content", async () => {
    // Arrange
    renderComposer();
    const input = screen.getByPlaceholderText(/reply/i);

    // Act
    await userEvent.type(input, "hi");
    await userEvent.click(screen.getByRole("button", { name: "@qa" }));

    // Assert
    expect(input).toHaveValue("hi @qa ");
  });
});
