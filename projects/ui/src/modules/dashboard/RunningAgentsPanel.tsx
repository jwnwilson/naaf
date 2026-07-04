import { Card } from "../../components/ui/Card";
import { ProgressBar } from "../../components/ui/ProgressBar";
import { PulseDot } from "../../components/ui/PulseDot";
import { useAgents } from "../../lib/api/hooks/useAgents";
import type { Agent } from "../../lib/api/hooks/useAgents";

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function RunningRow({ agent }: { agent: Agent }) {
  return (
    <div className="flex items-center gap-3 px-[15px] py-3">
      <PulseDot />
      <div className="flex-1 min-w-0">
        <div className="text-[11px] font-semibold text-text-2 truncate">{agent.role}</div>
        {agent.currentStage && (
          <div className="text-[10px] text-text-5 truncate">
            <span>{agent.workItemId ?? "—"}</span>
            <span> · </span>
            <span>{agent.currentStage}</span>
          </div>
        )}
        {agent.progress != null && (
          <div className="mt-1">
            <ProgressBar value={agent.progress} height={2} />
          </div>
        )}
      </div>
      <span className="font-mono text-[10px] text-text-5 shrink-0">
        {formatTokens(agent.tokenUsage)}
      </span>
    </div>
  );
}

function IdleRow({ agent }: { agent: Agent }) {
  return (
    <div className="flex items-center gap-3 px-[15px] py-3">
      <span
        className="rounded-full border border-[#2e3038] shrink-0"
        style={{ width: 6, height: 6 }}
      />
      <div className="flex-1 min-w-0">
        <div className="text-[11px] text-text-5 truncate">{agent.role}</div>
      </div>
      <span className="font-mono text-[10px] text-text-5 shrink-0">{agent.model}</span>
    </div>
  );
}

export function RunningAgentsPanel() {
  const { data: agents, isLoading } = useAgents();

  if (isLoading || !agents) {
    return (
      <div className="bg-bg-surface border border-border rounded-[8px] p-[15px] h-[200px] animate-pulse" />
    );
  }

  const runningAgents = agents.filter((a) => a.status === "running");
  const idleAgents = agents.filter((a) => a.status !== "running");

  return (
    <Card>
      <div className="flex items-center gap-2 px-[15px] pt-[15px] pb-3 border-b border-border">
        <span className="text-[12.5px] font-semibold text-text-2">Running Agents</span>
        <span className="text-[11px] text-[#4a8c68]">{runningAgents.length} active</span>
      </div>
      <div className="divide-y divide-[rgba(255,255,255,0.05)]">
        {runningAgents.map((agent) => (
          <RunningRow key={agent.role} agent={agent} />
        ))}
        {idleAgents.map((agent) => (
          <IdleRow key={agent.role} agent={agent} />
        ))}
      </div>
    </Card>
  );
}
