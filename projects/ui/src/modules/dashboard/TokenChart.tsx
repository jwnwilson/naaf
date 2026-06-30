import { Card } from "../../components/ui/Card";
import { useTokenUsage } from "../../lib/api/hooks/useDashboard";
import type { TokenUsagePoint } from "../../lib/api/hooks/useDashboard";

function toLocalDateString(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function BarColumn({ point, isToday, maxTokens }: {
  point: TokenUsagePoint;
  isToday: boolean;
  maxTokens: number;
}) {
  const heightPct = maxTokens > 0 ? (point.tokens / maxTokens) * 100 : 0;
  const dayLabel = new Date(point.day + "T12:00:00").toLocaleDateString("en-US", { weekday: "short" }).slice(0, 1);

  return (
    <div className="flex flex-col items-center gap-1 flex-1">
      <div className="w-full flex items-end" style={{ height: 64 }}>
        <div
          className="w-full rounded-[2px_2px_0_0]"
          style={{
            height: `${heightPct}%`,
            minHeight: point.tokens > 0 ? 2 : 0,
            background: isToday ? "#7c6cf0" : "#1e2028",
          }}
        />
      </div>
      <span
        className="font-mono text-[9px]"
        style={{ color: isToday ? "#7c6cf0" : "#25272e" }}
      >
        {dayLabel}
      </span>
    </div>
  );
}

export function TokenChart() {
  const { data: points, isLoading } = useTokenUsage();

  if (isLoading || !points) {
    return (
      <div className="bg-bg-surface border border-border rounded-[8px] p-[15px] h-[120px] animate-pulse" />
    );
  }

  const today = toLocalDateString(new Date());
  const maxTokens = Math.max(...points.map((p) => p.tokens), 1);

  return (
    <Card className="p-[15px]">
      <div className="text-[11px] font-semibold text-text-2 mb-3">Token Usage</div>
      <div className="flex items-end gap-1">
        {points.map((point) => (
          <BarColumn
            key={point.day}
            point={point}
            isToday={point.day === today}
            maxTokens={maxTokens}
          />
        ))}
      </div>
    </Card>
  );
}
