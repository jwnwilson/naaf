import { Card } from "../../components/ui/Card";
import { useActivity } from "../../lib/api/hooks/useDashboard";
import type { ActivityEvent } from "../../lib/api/hooks/useDashboard";

const WRITE_TYPES = new Set<ActivityEvent["type"]>(["agent_write", "run_complete"]);

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
}

function ActivityRow({ event }: { event: ActivityEvent }) {
  const isWrite = WRITE_TYPES.has(event.type);

  return (
    <div className="flex items-start gap-2 px-[15px] py-2">
      <span
        className="mt-[4px] rounded-full shrink-0"
        style={{
          width: 5,
          height: 5,
          background: isWrite ? "#7c6cf0" : "#2e3038",
        }}
      />
      <span className="flex-1 text-[11.5px] text-[#8a8d96] leading-snug">
        {event.description}
      </span>
      <span className="font-mono text-[9px] text-[#25272e] shrink-0 mt-[2px]">
        {formatTimestamp(event.createdAt)}
      </span>
    </div>
  );
}

export function ActivityFeed() {
  const { data: events, isLoading } = useActivity();

  if (isLoading || !events) {
    return (
      <div className="bg-bg-surface border border-border rounded-[8px] flex-1 h-[120px] animate-pulse" />
    );
  }

  return (
    <Card className="flex-1">
      <div className="flex items-center px-[15px] pt-[15px] pb-3 border-b border-border">
        <span className="text-[12.5px] font-semibold text-text-2">Activity</span>
      </div>
      <div className="divide-y divide-[rgba(255,255,255,0.05)]">
        {events.length === 0 ? (
          <div className="px-[15px] py-3 text-[11px] text-text-5">No recent activity.</div>
        ) : (
          events.map((event) => <ActivityRow key={event.id} event={event} />)
        )}
      </div>
    </Card>
  );
}
