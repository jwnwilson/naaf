import { Link } from "react-router-dom";
import { Avatar } from "../../components/ui";
import { LineageBreadcrumb } from "./LineageBreadcrumb";
import type { WorkItem } from "./groupByStatus";

function agentInitials(agentId: string): string {
  const parts = agentId.split("-").filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return agentId.slice(0, 2).toUpperCase();
}

export function KanbanCard({ item }: { item: WorkItem }) {
  const isInProgress = item.status === "in_progress";
  const borderClass = isInProgress ? "border border-accent-border" : "border border-border";

  return (
    <Link
      to={`/projects/${item.projectId}/items/${item.id}`}
      className={`block rounded-[7px] bg-[#141618] p-[10px] ${borderClass} no-underline`}
    >
      {/* Row 1: key + agent avatar */}
      <div className="flex items-center justify-between mb-[6px]">
        <span className="font-mono text-[9.5px] text-text-6">{item.key}</span>
        {item.assignedAgent && (
          <Avatar initials={agentInitials(item.assignedAgent.id)} variant="agent" size={17} />
        )}
      </div>

      {/* Row 2: title */}
      <p className="text-[12px] text-[#c8c9ce] leading-[1.4] mb-[8px] line-clamp-2">{item.title}</p>

      {/* Row 3: lineage + token count */}
      <div className="flex items-center gap-[6px] min-w-0">
        <LineageBreadcrumb item={item} />
        {item.tokenUsageThisRun != null && (
          <span className={`font-mono text-[9px] ${isInProgress ? "text-accent" : "text-text-6"}`}>
            {(item.tokenUsageThisRun / 1000).toFixed(1)}k
          </span>
        )}
      </div>
    </Link>
  );
}
