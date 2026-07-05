import { NavLink } from "react-router-dom";
import { Avatar } from "../components/ui/Avatar";
import { ProgressBar } from "../components/ui/ProgressBar";
import {
  DashboardIcon,
  GitRepoIcon,
  InboxIcon,
  ProjectsIcon,
  SearchIcon,
  SettingsIcon,
} from "../components/ui/icons";
import { useBudget } from "../lib/api/hooks/useBudget";
import { useDashboard } from "../lib/api/hooks/useDashboard";
import { useProjects } from "../lib/api/hooks/useProjects";
import type { Project } from "../lib/api/hooks/useProjects";
import { useCreateModal } from "../modules/create/useCreateModal";

// ── NavItem ────────────────────────────────────────────────────────────────────

interface NavItemProps {
  to: string;
  icon: React.ReactNode;
  label: string;
  badge?: React.ReactNode;
}

function NavItem({ to, icon, label, badge }: NavItemProps) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        [
          "flex items-center gap-[7px] rounded-[5px] px-[7px] py-[5px] text-[11px] transition-colors",
          isActive
            ? "bg-accent-bg text-accent-text font-medium"
            : "text-[#4a4d56] hover:text-[#8a8d96]",
        ].join(" ")
      }
    >
      {icon}
      <span className="flex-1">{label}</span>
      {badge}
    </NavLink>
  );
}



// ── ProjectRow ─────────────────────────────────────────────────────────────────

function ProjectRow({ project }: { project: Project }) {
  return (
    <NavLink
      to={`/projects?project=${project.id}`}
      className={({ isActive }) =>
        [
          "flex items-center gap-[6px] rounded-[5px] px-[7px] py-[5px] text-[11.5px] transition-colors",
          isActive
            ? "bg-[rgba(124,108,240,0.08)] text-accent-text"
            : "text-[#42454e] hover:text-[#8a8d96]",
        ].join(" ")
      }
    >
      {({ isActive }) => (
        <>
          <GitRepoIcon size={11} className="shrink-0" />
          <span className="flex-1 truncate">{project.name}</span>
          <span
            className={`font-mono text-[9px] ${isActive ? "text-accent" : "text-[#4a4d56]"}`}
          >
            {project.itemCount}
          </span>
        </>
      )}
    </NavLink>
  );
}

// ── Sidebar ────────────────────────────────────────────────────────────────────

export function Sidebar() {
  const projectsQuery = useProjects();
  const budgetQuery = useBudget();
  const dashboardQuery = useDashboard();
  const { openCreateProject } = useCreateModal();

  const projects = projectsQuery.data?.results ?? [];
  const budget = budgetQuery.data;
  const activeAgents = dashboardQuery.data?.activeAgents ?? 0;

  return (
    <nav className="flex h-full w-[214px] shrink-0 flex-col border-r border-[rgba(255,255,255,0.055)] bg-bg-sidebar">
      {/* Workspace header */}
      <div className="flex h-[48px] shrink-0 items-center gap-[8px] px-[9px]">
        <Avatar initials="JW" size={24} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[12.5px] font-semibold text-text-1">Noel Wilson</div>
          <div className="font-mono text-[9px] text-[#30333c]">naaf workspace</div>
        </div>
      </div>

      {/* Search bar */}
      <div className="px-[9px] pb-[8px]">
        <div className="flex h-[28px] items-center gap-[6px] rounded-[5px] border border-border bg-bg-input px-[8px]">
          <SearchIcon size={11} className="shrink-0 text-[#30333c]" />
          <span className="flex-1 text-[11.5px] text-[#30333c]">Search…</span>
          <span className="font-mono text-[9px] text-[#20222a]">⌘K</span>
        </div>
      </div>

      {/* Nav items */}
      <div className="flex flex-col gap-[2px] px-[6px]">
        <NavItem
          to="/dashboard"
          icon={<DashboardIcon size={13} />}
          label="Dashboard"
          badge={
            activeAgents > 0 ? (
              <span className="flex items-center gap-[5px] font-mono text-[9.5px] text-[#4a8c68]">
                <span
                  data-testid="dashboard-running-dot"
                  className="inline-block rounded-full bg-[#4a8c68]"
                  style={{ width: 6, height: 6 }}
                />
                {activeAgents}
              </span>
            ) : undefined
          }
        />
        <NavItem
          to="/inbox"
          icon={<InboxIcon size={13} />}
          label="Inbox"
        />
        <NavItem
          to="/projects"
          icon={<ProjectsIcon size={13} />}
          label="Projects"
        />
      </div>

      {/* Projects section */}
      <div className="mt-[14px] flex flex-col gap-[2px] px-[6px]">
        <div className="flex items-center justify-between px-[7px] pb-[4px]">
          <span className="font-mono text-[9.5px] tracking-[0.08em] text-[#20222a]">PROJECTS</span>
          <button
            type="button"
            aria-label="New project"
            onClick={() => openCreateProject()}
            className="text-[#20222a] hover:text-[#8a8d96] text-[13px] leading-none"
          >
            +
          </button>
        </div>
        {projects.map((project) => (
          <ProjectRow key={project.id} project={project} />
        ))}
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Settings + budget footer */}
      <div className="border-t border-[rgba(255,255,255,0.05)]">
        <div className="px-[6px] pt-[4px]">
          <NavItem
            to="/settings/agents"
            icon={<SettingsIcon size={13} />}
            label="Settings"
          />
        </div>
        {budget && (
          <div className="px-[9px] pb-[10px] pt-[6px]">
            <div className="mb-[4px] flex items-center justify-between">
              <span className="font-mono text-[9.5px] text-[#30333c]">BUDGET</span>
              <span className="font-mono text-[9.5px] text-[#72757e]">
                ${budget.used.toFixed(2)} / ${budget.limit.toFixed(0)}
              </span>
            </div>
            <ProgressBar value={budget.limit > 0 ? budget.used / budget.limit : 0} />
          </div>
        )}
      </div>
    </nav>
  );
}
