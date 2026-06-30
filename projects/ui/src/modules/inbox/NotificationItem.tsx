import { Avatar } from "../../components/ui/Avatar";
import { StatusBadge } from "../../components/ui/StatusBadge";
import type { components } from "../../lib/api/schema";

type InboxItem = components["schemas"]["InboxItem"];

interface NotificationItemProps {
  item: InboxItem;
  selected: boolean;
  onSelect: (id: string) => void;
}

function formatTimestamp(iso: string): string {
  if (!iso) return "";
  const date = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60_000);
  if (diffMins < 60) return `${diffMins}m`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h`;
  return `${Math.floor(diffHours / 24)}d`;
}

function agentInitials(agentId: string): string {
  return agentId.replace("agent-", "A").toUpperCase();
}

export function NotificationItem({ item, selected, onSelect }: NotificationItemProps) {
  const isResolved = item.type === "resolved";
  const titleColor = item.read ? "#c0c2c8" : "#e2e3e8";

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onSelect(item.id)}
      onKeyDown={(e) => e.key === "Enter" && onSelect(item.id)}
      className="cursor-pointer border-b border-[rgba(255,255,255,0.06)]"
      style={{
        padding: "13px 14px",
        background: selected ? "rgba(124,108,240,0.06)" : "transparent",
        borderLeft: selected ? "2px solid #7c6cf0" : "2px solid transparent",
        opacity: isResolved ? 0.4 : 1,
      }}
    >
      <div className="flex items-start justify-between gap-2 mb-1">
        <StatusBadge kind={item.type} />
        <span className="font-mono text-[9px] text-[#30333c] shrink-0">
          {formatTimestamp(item.createdAt)}
        </span>
      </div>

      <p
        className="text-[12.5px] font-medium mb-1 truncate"
        style={{ color: titleColor, fontWeight: item.read ? 400 : 500 }}
      >
        {item.title}
      </p>

      <p className="text-[11px] text-[#52555e] truncate mb-2">{item.preview}</p>

      <div className="flex items-center gap-1.5 text-[10.5px]">
        <Avatar initials={agentInitials(item.agentId)} variant="agent" size={16} />
        <span className="text-[#52555e]">{item.agentId}</span>
        <span className="text-[#52555e]">·</span>
        <span className="text-[#7c6cf0] font-mono">{item.workItemId}</span>
      </div>
    </div>
  );
}
