import { useThreads } from "../../lib/api/hooks";
import { NotificationItem } from "./NotificationItem";

interface InboxListProps {
  selectedId?: string;
  onSelect: (id: string) => void;
}

export function InboxList({ selectedId, onSelect }: InboxListProps) {
  const { data: threads = [], isLoading } = useThreads();

  return (
    <div className="flex flex-col h-full" style={{ width: 356, minWidth: 356 }}>
      {/* Header */}
      <div
        className="flex items-center shrink-0 px-[14px]"
        style={{ height: 44, borderBottom: "1px solid rgba(255,255,255,0.06)" }}
      >
        <h2 className="text-[13px] font-semibold text-[#c4c5cb]">Inbox</h2>
      </div>

      {/* Thread rows */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && (
          <p className="text-[11px] text-[#30333c] px-[14px] py-[10px]">Loading…</p>
        )}
        {!isLoading && threads.length === 0 && (
          <p className="text-[11px] text-[#30333c] px-[14px] py-[10px]">No conversations</p>
        )}
        {!isLoading &&
          threads.map((thread) => (
            <NotificationItem
              key={thread.id}
              item={thread}
              selected={thread.id === selectedId}
              onSelect={onSelect}
            />
          ))}
      </div>
    </div>
  );
}
