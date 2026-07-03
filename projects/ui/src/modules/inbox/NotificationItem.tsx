import { Avatar } from "../../components/ui/Avatar";
import type { Thread } from "../../lib/api/hooks";

interface NotificationItemProps {
  item: Thread;
  selected: boolean;
  onSelect: (id: string) => void;
}

export function NotificationItem({ item, selected, onSelect }: NotificationItemProps) {
  const participant = item.participants[0] ?? "user";
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
        <Avatar initials={participant.slice(0, 2).toUpperCase()} variant="agent" size={16} />
        <p className="text-[12.5px] font-medium text-[#e2e3e8] truncate">{item.title}</p>
      </div>
      {item.lastMessage && (
        <p className="text-[11px] text-[#52555e] truncate">{item.lastMessage}</p>
      )}
    </div>
  );
}
