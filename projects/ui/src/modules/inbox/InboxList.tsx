import { useState } from "react";
import { useInbox } from "../../lib/api/hooks/useInbox";
import { NotificationItem } from "./NotificationItem";

type FilterTab = "All" | "Action needed" | "Info" | "Resolved";

const FILTER_TABS: FilterTab[] = ["All", "Action needed", "Info", "Resolved"];

function tabToType(tab: FilterTab): string | undefined {
  switch (tab) {
    case "Action needed": return "action_needed";
    case "Info": return "info";
    case "Resolved": return "resolved";
    default: return undefined;
  }
}

interface InboxListProps {
  selectedId?: string;
  onSelect: (id: string) => void;
}

export function InboxList({ selectedId, onSelect }: InboxListProps) {
  const [activeTab, setActiveTab] = useState<FilterTab>("All");
  const { data: items, isLoading } = useInbox(tabToType(activeTab));

  const rows = items?.results ?? [];
  const unreadCount = rows.filter((i) => !i.read).length;

  return (
    <div className="flex flex-col h-full" style={{ width: 356, minWidth: 356 }}>
      {/* Header */}
      <div
        className="flex items-center justify-between shrink-0 px-[14px]"
        style={{ height: 44, borderBottom: "1px solid rgba(255,255,255,0.06)" }}
      >
        <div className="flex items-center gap-2">
          <h2 className="text-[13px] font-semibold text-[#c4c5cb]">Inbox</h2>
          {unreadCount > 0 && (
            <span
              className="font-mono text-[10px] text-[#bab7f6] px-[6px] py-[2px]"
              style={{
                background: "rgba(124,108,240,0.10)",
                borderRadius: 8,
              }}
            >
              {unreadCount}
            </span>
          )}
        </div>
        <button
          className="text-[11px] text-[#52555e] hover:text-[#8a8d96] transition-colors"
          onClick={() => {}}
        >
          Mark all read
        </button>
      </div>

      {/* Filter tabs */}
      <div
        className="flex items-center gap-0 shrink-0 px-[10px]"
        style={{
          height: 36,
          borderBottom: "1px solid rgba(255,255,255,0.06)",
        }}
      >
        {FILTER_TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className="text-[11.5px] px-[8px] py-[4px] rounded-[4px] transition-colors"
            style={{
              color: activeTab === tab ? "#bab7f6" : "#52555e",
              background: activeTab === tab ? "rgba(124,108,240,0.10)" : "transparent",
              fontWeight: activeTab === tab ? 500 : 400,
            }}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Notification rows */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && (
          <p className="text-[11px] text-[#30333c] px-[14px] py-[10px]">Loading…</p>
        )}
        {!isLoading && rows.length === 0 && (
          <p className="text-[11px] text-[#30333c] px-[14px] py-[10px]">No notifications</p>
        )}
        {!isLoading &&
          rows.map((item) => (
            <NotificationItem
              key={item.id}
              item={item}
              selected={item.id === selectedId}
              onSelect={onSelect}
            />
          ))}
      </div>
    </div>
  );
}
