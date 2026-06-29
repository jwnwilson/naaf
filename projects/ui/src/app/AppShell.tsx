import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";

export function AppShell() {
  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <header data-topbar className="h-[44px] shrink-0 border-b border-border" />
        <main className="flex-1 overflow-auto p-4">
          <Outlet />
        </main>
      </div>
      <aside data-chat className="w-[320px] shrink-0 border-l border-border" />
    </div>
  );
}
