import { MetricCard } from "../../components/ui/MetricCard";
import { ProgressBar } from "../../components/ui/ProgressBar";
import { useAgents } from "../../lib/api/hooks/useAgents";
import { useBudget } from "../../lib/api/hooks/useBudget";
import { useDashboard } from "../../lib/api/hooks/useDashboard";

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function SpendCardSub({ pct }: { pct: number }) {
  return (
    <div className="mt-2 space-y-1">
      <ProgressBar value={pct} />
      <span className="font-mono text-[9.5px] text-accent">
        {Math.round(pct * 100)}%
      </span>
    </div>
  );
}

export function MetricCards() {
  const { data: metrics, isLoading } = useDashboard();
  const { data: budget } = useBudget();
  const { data: agents } = useAgents();
  const activeCount = (agents ?? []).filter((a) => a.status === "running").length;

  if (isLoading || !metrics) {
    return (
      <div className="grid grid-cols-4 gap-3">
        {Array.from({ length: 4 }, (_, i) => (
          <div
            key={i}
            className="bg-bg-surface border border-border rounded-[8px] p-[15px] h-[90px] animate-pulse"
          />
        ))}
      </div>
    );
  }

  const spendPct = budget ? Math.min(1, budget.used / budget.limit) : 0;

  return (
    <div className="grid grid-cols-4 gap-3">
      <MetricCard
        label="ACTIVE AGENTS"
        value={activeCount}
        sub={
          <span className="flex items-center gap-[5px] text-[#4a8c68]">
            {activeCount > 0 && (
              <span
                data-testid="active-agents-dot"
                className="inline-block rounded-full bg-[#4a8c68]"
                style={{ width: 6, height: 6 }}
              />
            )}
            {activeCount} running now
          </span>
        }
      />
      <MetricCard
        label="TOTAL SPEND"
        value={`$${metrics.totalSpend.toFixed(2)}`}
        accent
        sub={<SpendCardSub pct={spendPct} />}
      />
      <MetricCard
        label="TOTAL TOKENS"
        value={formatTokens(metrics.totalTokens)}
        sub="total consumed"
      />
      <MetricCard
        label="PROJECTS"
        value={metrics.projectCount}
        sub={`${metrics.workItemCount} work items`}
      />
    </div>
  );
}
