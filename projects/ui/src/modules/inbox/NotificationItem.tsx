import { Avatar } from "../../components/ui/Avatar";
import type { Thread } from "../../lib/api/hooks";

interface NotificationItemProps {
  item: Thread;
  selected: boolean;
  onSelect: (id: string) => void;
}

function agentInitials(agentId: string): string {
  return agentId.replace("agent-", "A").toUpperCase();
}

export function NotificationItem({ item, selected, onSelect }: NotificationItemProps) {
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
      }}
    >
      <div className="flex items-center gap-1.5 mb-1">
        <Avatar initials={agentInitials(item.agentId)} variant="agent" size={16} />
        <p className="text-[12.5px] font-medium text-[#e2e3e8]">{item.agentId}</p>
      </div>
      <p className="text-[11px] text-[#52555e] font-mono truncate">{item.workItemId}</p>
    </div>
  );
}
