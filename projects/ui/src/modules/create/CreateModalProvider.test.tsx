import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";
import { server } from "../../lib/api/mocks/server";
import { CreateModalProvider } from "./CreateModalProvider";
import { useCreateModal } from "./useCreateModal";

import type { components } from "../../lib/api/schema";

const editItem = {
  id: "w1", type: "task", title: "Add auth", status: "todo", priority: "medium",
  projectId: "p1", spec: "", createdAt: "", updatedAt: "",
} as components["schemas"]["WorkItem"];

const editProject = {
  id: "p1", name: "Acme", description: "", repoUrl: "", itemCount: 0, createdAt: "", updatedAt: "",
} as components["schemas"]["Project"];

function Harness() {
  const { openCreateProject, openCreateWorkItem, openEditWorkItem, openEditProject } = useCreateModal();
  return (
    <>
      <button onClick={() => openCreateProject()}>open project</button>
      <button onClick={() => openCreateWorkItem({ projectId: "p1" })}>open item</button>
      <button onClick={() => openEditWorkItem(editItem)}>open edit</button>
      <button onClick={() => openEditProject(editProject)}>open edit project</button>
    </>
  );
}

function renderProvider() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  server.use(
    http.get("/api/work-items", () =>
      HttpResponse.json({ success: true, error: null, data: [], meta: { total: 0, page_size: 50, page_number: 1 } }),
    ),
  );
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <CreateModalProvider>
          <Harness />
        </CreateModalProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("opens the Create Project modal", async () => {
  renderProvider();
  await userEvent.click(screen.getByText("open project"));
  expect(screen.getByRole("dialog")).toHaveTextContent("Create Project");
});

test("opens the Create Work Item modal", async () => {
  renderProvider();
  await userEvent.click(screen.getByText("open item"));
  expect(screen.getByRole("dialog")).toHaveTextContent("Create Work Item");
});

test("opens the Edit Work Item modal pre-filled", async () => {
  renderProvider();
  await userEvent.click(screen.getByText("open edit"));
  expect(screen.getByRole("dialog")).toHaveTextContent("Edit Work Item");
  expect((screen.getByLabelText(/title/i) as HTMLInputElement).value).toBe("Add auth");
});

test("opens the Edit Project modal pre-filled", async () => {
  renderProvider();
  await userEvent.click(screen.getByText("open edit project"));
  expect(screen.getByRole("dialog")).toHaveTextContent("Edit Project");
  expect((screen.getByLabelText(/name/i) as HTMLInputElement).value).toBe("Acme");
});

test("closing the modal removes it", async () => {
  renderProvider();
  await userEvent.click(screen.getByText("open project"));
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("useCreateModal throws when used outside the provider", () => {
  const spy = vi.spyOn(console, "error").mockImplementation(() => {});
  expect(() => render(<Harness />)).toThrow("useCreateModal must be used within CreateModalProvider");
  spy.mockRestore();
});
