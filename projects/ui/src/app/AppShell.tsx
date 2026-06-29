import { Outlet } from "react-router-dom";

export function AppShell() {
  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <aside data-sidebar className="w-[214px] shrink-0 border-r border-border" />
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
