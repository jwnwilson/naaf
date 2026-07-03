// src/app/AppShell.tsx  (full replacement)
import { Outlet, useLocation, useSearchParams } from "react-router-dom";
import { CreateModalProvider } from "../modules/create/CreateModalProvider";
import { useCreateModal } from "../modules/create/useCreateModal";
import { useCurrentProjectId } from "../lib/hooks/useCurrentProjectId";
import { ChatPanel } from "./ChatPanel";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

type View = "board" | "list";

function isView(v: string | null): v is View {
  return v === "board" || v === "list";
}

const ROUTE_TITLES: Record<string, string> = {
  "/dashboard": "Dashboard",
  "/inbox": "Inbox",
  "/projects": "Projects",
  "/settings/agents": "Settings",
};

function usePageTitle(): string {
  const { pathname } = useLocation();
  if (ROUTE_TITLES[pathname]) return ROUTE_TITLES[pathname];
  if (pathname.startsWith("/projects/")) return "Projects";
  return "Projects";
}

function AppShellLayout() {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawView = searchParams.get("view");
  const view: View = isView(rawView) ? rawView : "board";
  const title = usePageTitle();
  const projectId = useCurrentProjectId();
  const { openCreateProject, openCreateWorkItem } = useCreateModal();

  function handleViewChange(next: View) {
    setSearchParams((prev) => {
      const updated = new URLSearchParams(prev);
      updated.set("view", next);
      return updated;
    });
  }

  function handleNew() {
    if (projectId) openCreateWorkItem({ projectId });
    else openCreateProject();
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-bg-base text-text-1">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Topbar title={title} count={0} view={view} onViewChange={handleViewChange} onNew={handleNew} />
        <main className="flex-1 overflow-auto p-4">
          <Outlet />
        </main>
      </div>
      <ChatPanel />
    </div>
  );
}

export function AppShell() {
  return (
    <CreateModalProvider>
      <AppShellLayout />
    </CreateModalProvider>
  );
}
