import { Outlet, useSearchParams } from "react-router-dom";
import { ChatPanel } from "./ChatPanel";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

type View = "board" | "list";

function isView(v: string | null): v is View {
  return v === "board" || v === "list";
}

export function AppShell() {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawView = searchParams.get("view");
  const view: View = isView(rawView) ? rawView : "board";

  function handleViewChange(next: View) {
    setSearchParams((prev) => {
      const updated = new URLSearchParams(prev);
      updated.set("view", next);
      return updated;
    });
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Topbar
          title="Projects"
          count={0}
          view={view}
          onViewChange={handleViewChange}
          onNew={() => {}}
        />
        <main className="flex-1 overflow-auto p-4">
          <Outlet />
        </main>
      </div>
      <ChatPanel />
    </div>
  );
}
