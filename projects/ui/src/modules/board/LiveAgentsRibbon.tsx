import { ProgressBar } from "../../components/ui/ProgressBar";
import { PulseDot } from "../../components/ui/PulseDot";
import { useAgents } from "../../lib/api/hooks";
import type { Agent } from "../../lib/api/hooks";

function RunningChip({ agent }: { agent: Agent }) {
  return (
    <div
      className="flex flex-col gap-[3px] min-w-[170px] rounded-[7px] border border-[rgba(255,255,255,0.07)] bg-[#131618]"
      style={{ padding: "9px 11px" }}
    >
      <div className="flex items-center gap-[6px]">
        <PulseDot size={6} className="shrink-0" />
        <span className="flex-1 truncate text-[11px] font-semibold text-[#c4c5cb]">
          {agent.name}
        </span>
        <span className="shrink-0 font-mono text-[8.5px] text-[#7c6cf0]">RUN</span>
      </div>
      <div className="truncate text-[10px] text-[#4a4d56]">
        {agent.currentItemId ?? "—"}
      </div>
      <ProgressBar value={agent.progress ?? 0} height={2} />
    </div>
  );
}

function IdleChip({ agent }: { agent: Agent }) {
  return (
    <div
      className="flex flex-col gap-[3px] min-w-[132px] rounded-[7px] border border-[rgba(255,255,255,0.05)] bg-[#0e0f11]"
      style={{ padding: "9px 11px" }}
    >
      <div className="flex items-center gap-[6px]">
        <span
          className="shrink-0 rounded-full border border-[#2e3038]"
          style={{ width: 6, height: 6 }}
        />
        <span className="flex-1 truncate text-[11px] text-[#30333c]">
          {agent.name}
        </span>
        <span className="shrink-0 font-mono text-[8.5px] text-[#22252c]">IDLE</span>
      </div>
      <div className="text-[10px] text-[#22252c]">Awaiting task</div>
    </div>
  );
}

export function LiveAgentsRibbon() {
  const { data } = useAgents();
  const agents = data ?? [];

  return (
    <div
      className="flex items-center gap-3 overflow-x-auto border-b border-[rgba(255,255,255,0.055)] bg-[#0b0c0f] px-4"
      style={{ height: 76 }}
    >
      <span className="shrink-0 font-mono text-[9.5px] tracking-[0.08em] text-[#28292e]">
        LIVE AGENTS
      </span>
      {agents.map((agent) =>
        agent.status === "running" ? (
          <RunningChip key={agent.id} agent={agent} />
        ) : (
          <IdleChip key={agent.id} agent={agent} />
        ),
      )}
    </div>
  );
}
