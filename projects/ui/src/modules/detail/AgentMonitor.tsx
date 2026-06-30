import { Avatar, ProgressBar, PulseDot, StatusBadge } from "../../components/ui";
import { useAgents } from "../../lib/api/hooks";
import { useRun } from "../../lib/api/hooks/useRun";
import { LogStream } from "./LogStream";
import { StepTimeline } from "./StepTimeline";

const FALLBACK_TOKEN_LIMIT = 200_000;

function formatTokens(n: number): string {
  return n >= 1_000 ? `${(n / 1_000).toFixed(1)}k` : String(n);
}

function agentInitials(agentId: string): string {
  const parts = agentId.split("-");
  if (parts.length >= 2) {
    return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  }
  return agentId.slice(0, 2).toUpperCase();
}

export function AgentMonitor({ runId }: { runId: string }) {
  const { run, logLines, isStreaming } = useRun(runId);
  const { data: agents } = useAgents();

  if (!run) {
    return (
      <div className="flex items-center justify-center p-8 font-mono text-[11px] text-[#42454e]">
        Loading…
      </div>
    );
  }

  const agent = agents?.find((a) => a.id === run.agentId);
  const agentLabel = agent?.name ?? run.agentId;
  const tokenLimit = run.tokenLimit ?? FALLBACK_TOKEN_LIMIT;
  const tokenFraction = Math.min(run.tokenUsage / tokenLimit, 1);

  return (
    <div className="flex flex-col h-full">
      {/* ── Header ────────────────────────────────────────────────────────── */}
      <div
        className="flex items-center gap-3 px-5 py-3 flex-shrink-0"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.07)" }}
      >
        <Avatar initials={agentInitials(run.agentId)} variant="agent" size={22} />

        <div className="flex flex-col" style={{ gap: 2 }}>
          <span className="text-[11px] font-semibold text-text-1">{agentLabel}</span>
          <span className="font-mono text-[9.5px]" style={{ color: "#42454e" }}>
            {run.status}
          </span>
        </div>

        <div className="flex items-center gap-1.5 ml-2">
          {isStreaming && <PulseDot size={6} />}
          <span className="animate-[pulse_3s_infinite]">
            <StatusBadge kind={isStreaming ? "running" : "idle"} />
          </span>
        </div>

        <div className="ml-auto flex gap-2">
          <button
            type="button"
            className="font-mono text-[9.5px] px-2 py-1 rounded"
            style={{
              background: "transparent",
              border: "1px solid rgba(255,255,255,0.09)",
              color: "#52555e",
            }}
          >
            Pause
          </button>
          <button
            type="button"
            className="font-mono text-[9.5px] px-2 py-1 rounded"
            style={{
              background: "transparent",
              border: "1px solid rgba(180,60,60,0.20)",
              color: "#b05848",
            }}
          >
            Stop
          </button>
        </div>
      </div>

      {/* ── Timeline ──────────────────────────────────────────────────────── */}
      <div
        className="flex-shrink-0"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}
      >
        <StepTimeline steps={run.steps} />
      </div>

      {/* ── Log stream ────────────────────────────────────────────────────── */}
      <div className="flex-1 px-5 py-3 min-h-0 overflow-hidden">
        <LogStream lines={logLines} />
      </div>

      {/* ── Token meter ───────────────────────────────────────────────────── */}
      <div
        className="flex items-center gap-3 px-5 py-2 flex-shrink-0"
        style={{ borderTop: "1px solid rgba(255,255,255,0.05)" }}
      >
        <span className="font-mono text-[10.5px] flex-shrink-0" style={{ color: "#3a3d44" }}>
          {formatTokens(run.tokenUsage)} / {formatTokens(tokenLimit)} tok
        </span>
        <div className="flex-1">
          <ProgressBar value={tokenFraction} />
        </div>
        <span className="font-mono text-[10.5px] flex-shrink-0" style={{ color: "#3a3d44" }}>
          ${run.cost.toFixed(4)}
        </span>
      </div>
    </div>
  );
}
