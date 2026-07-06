import { Link } from "react-router-dom";
import { Avatar, PriorityBars, StatusCircle } from "../../components/ui";
import { LineageBreadcrumb } from "./LineageBreadcrumb";
import type { WorkItem } from "./groupByStatus";

function formatAge(createdAt: string): string {
  if (!createdAt) return "";
  const diffMs = Date.now() - new Date(createdAt).getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return "0d";
  if (diffDays < 30) return `${diffDays}d`;
  return `${Math.floor(diffDays / 30)}mo`;
}

function agentInitials(agentId: string): string {
  const parts = agentId.split("-").filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return agentId.slice(0, 2).toUpperCase();
}

export function ListRow({ item }: { item: WorkItem }) {
  return (
    <Link
      to={`/projects/${item.projectId}/items/${item.id}`}
      className="flex h-[34px] items-center gap-[8px] border-b border-[rgba(255,255,255,0.03)] px-[14px] no-underline hover:bg-bg-overlay"
    >
      <PriorityBars priority={item.priority} />
      <StatusCircle status={item.status} />
      <span className="w-[62px] shrink-0 font-mono text-[10.5px] text-text-6">{item.key}</span>
      <span className="min-w-0 flex-1 truncate text-[12.5px] text-[#b0b2b8]">{item.title}</span>
      <LineageBreadcrumb item={item} />
      {item.tokenUsageThisRun != null && (
        <span className="w-[44px] shrink-0 text-right font-mono text-[10px] text-text-6">
          {(item.tokenUsageThisRun / 1000).toFixed(1)}k
        </span>
      )}
      {item.assignedAgent != null ? (
        <Avatar initials={agentInitials(item.assignedAgent.id)} variant="agent" size={18} />
      ) : (
        <span className="inline-block w-[18px] shrink-0" aria-hidden="true" />
      )}
      <span className="w-[24px] shrink-0 text-right font-mono text-[10px] text-text-6">
        {formatAge(item.createdAt)}
      </span>
    </Link>
  );
}
