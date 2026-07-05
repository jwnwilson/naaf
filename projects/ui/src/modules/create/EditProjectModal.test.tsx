import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { expect, test, vi } from "vitest";
import { server } from "../../lib/api/mocks/server";
import { EditProjectModal } from "./EditProjectModal";
import type { components } from "../../lib/api/schema";

const project = {
  id: "p1", name: "Acme", description: "old desc", repoUrl: "https://x/y",
  itemCount: 3, createdAt: "", updatedAt: "",
} as components["schemas"]["Project"];

function renderModal(onClose = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <EditProjectModal project={project} onClose={onClose} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { onClose };
}

test("prefills fields from the project", () => {
  renderModal();
  expect((screen.getByLabelText(/name/i) as HTMLInputElement).value).toBe("Acme");
  expect((screen.getByLabelText(/description/i) as HTMLTextAreaElement).value).toBe("old desc");
});

test("saves edits and closes", async () => {
  const receivedRef: { value: { description?: string } | null } = { value: null };
  server.use(
    http.patch("/api/projects/p1", async ({ request }) => {
      receivedRef.value = (await request.json()) as { description?: string };
      return HttpResponse.json({ success: true, error: null, data: { ...project, description: receivedRef.value.description ?? "" } });
    }),
  );
  const { onClose } = renderModal();
  const desc = screen.getByLabelText(/description/i);
  await userEvent.clear(desc);
  await userEvent.type(desc, "ship it");
  await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
  await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
  expect(receivedRef.value?.description).toBe("ship it");
});

test("delete is gated behind an inline confirm", async () => {
  const deleteCalled = vi.fn();
  server.use(
    http.delete("/api/projects/p1", () => {
      deleteCalled();
      return HttpResponse.json({ success: true, error: null, data: null });
    }),
  );
  const { onClose } = renderModal();

  await userEvent.click(screen.getByRole("button", { name: /^delete$/i }));
  expect(screen.getByText(/can't be undone/i)).toBeInTheDocument();
  expect(deleteCalled).not.toHaveBeenCalled();

  await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
  expect(screen.queryByText(/can't be undone/i)).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: /^delete$/i }));
  await userEvent.click(screen.getByRole("button", { name: /confirm delete/i }));
  await waitFor(() => expect(deleteCalled).toHaveBeenCalledOnce());
  await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
});
