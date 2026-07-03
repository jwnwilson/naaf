import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { expect, test, vi } from "vitest";
import { server } from "../../lib/api/mocks/server";
import type { components } from "../../lib/api/schema";
import { EditWorkItemModal } from "./EditWorkItemModal";

type WorkItem = components["schemas"]["WorkItem"];

const item = {
  id: "w1", type: "task", title: "Add auth", status: "todo", priority: "medium",
  projectId: "p1", spec: "original spec", createdAt: "", updatedAt: "",
} as WorkItem;

function renderModal(overrides: Partial<WorkItem> = {}) {
  const onClose = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <EditWorkItemModal item={{ ...item, ...overrides }} onClose={onClose} />
    </QueryClientProvider>,
  );
  return { onClose };
}

test("pre-fills the form from the item", () => {
  renderModal();
  expect((screen.getByLabelText(/title/i) as HTMLInputElement).value).toBe("Add auth");
  expect((screen.getByLabelText(/priority/i) as HTMLSelectElement).value).toBe("medium");
  expect((screen.getByLabelText(/spec \/ description/i) as HTMLTextAreaElement).value).toBe("original spec");
});

test("Save is disabled when the title is emptied", async () => {
  renderModal();
  await userEvent.clear(screen.getByLabelText(/title/i));
  expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();
});

test("patches the edited fields and closes on save", async () => {
  let capturedBody: Record<string, unknown> = {};
  server.use(
    http.patch("/api/work-items/w1", async ({ request }) => {
      capturedBody = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({
        success: true, error: null,
        data: { ...item, title: capturedBody.title, priority: capturedBody.priority, spec: capturedBody.spec, updatedAt: "2026-07-03T00:00:00Z" },
      });
    }),
  );
  const { onClose } = renderModal();
  const title = screen.getByLabelText(/title/i);
  await userEvent.clear(title);
  await userEvent.type(title, "Add OAuth");
  await userEvent.selectOptions(screen.getByLabelText(/priority/i), "high");
  await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
  await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
  expect(capturedBody.title).toBe("Add OAuth");
  expect(capturedBody.priority).toBe("high");
  expect(capturedBody.spec).toBe("original spec");
});

test("surfaces an error and stays open when the patch fails", async () => {
  server.use(
    http.patch("/api/work-items/w1", () =>
      HttpResponse.json({ success: false, data: null, error: "boom" }, { status: 500 }),
    ),
  );
  const { onClose } = renderModal();
  await userEvent.click(screen.getByRole("button", { name: /^save$/i }));
  await waitFor(() => expect(screen.getByText(/boom/i)).toBeInTheDocument());
  expect(onClose).not.toHaveBeenCalled();
});
