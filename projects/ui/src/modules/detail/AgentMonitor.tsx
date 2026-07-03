import { Avatar, PulseDot, StatusBadge } from "../../components/ui";
import { useRun, useResolveGate } from "../../lib/api/hooks";
import { LogStream } from "./LogStream";
import { StepTimeline } from "./StepTimeline";

function formatTokens(n: number): string {
  return n >= 1_000 ? `${(n / 1_000).toFixed(1)}k` : String(n);
}

function roleInitials(role: string): string {
  return role.slice(0, 2).toUpperCase();
}

export function AgentMonitor({ runId }: { runId: string }) {
  const { run, events, isStreaming } = useRun(runId);
  const gate = useResolveGate(runId);

  if (!run) {
    return (
      <div className="flex items-center justify-center p-8 font-mono text-[11px] text-[#42454e]">
        Loading…
      </div>
    );
  }

  const currentStage = run.stages.find((s) => s.stage === run.currentStage);
  const role = currentStage?.role ?? "lead";
  const startedAt = run.startedAt
    ? new Date(run.startedAt).toISOString().slice(0, 19).replace("T", " ")
    : "—";

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div
        className="flex items-center gap-3 px-5 py-3 flex-shrink-0"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.07)" }}
      >
        <Avatar initials={roleInitials(role)} variant="agent" size={22} />
        <div className="flex flex-col" style={{ gap: 2 }}>
          <span className="text-[11px] font-semibold text-text-1">{role}</span>
          <span className="font-mono text-[9.5px]" style={{ color: "#42454e" }}>
            {run.status}
            {run.currentStage ? ` · ${run.currentStage}` : ""} · {startedAt}
          </span>
        </div>
        <div className="flex items-center gap-1.5 ml-2">
          {isStreaming && <PulseDot size={6} />}
          <StatusBadge kind={isStreaming ? "running" : "idle"} />
        </div>
        {run.prUrl && (
          <a
            href={run.prUrl}
            target="_blank"
            rel="noreferrer"
            className="ml-2 rounded-[5px] px-2 py-1 text-[10px] text-accent"
            style={{ background: "rgba(124,108,240,0.18)" }}
          >
            View PR ↗
          </a>
        )}
        <div className="flex flex-col items-end ml-auto" style={{ gap: 2 }}>
          <span className="font-mono text-[10px] text-text-1">
            {formatTokens(run.tokenUsage)} tok
          </span>
          <span className="font-mono text-[9px]" style={{ color: "#42454e" }}>
            ${run.cost.toFixed(4)}
          </span>
        </div>
      </div>

      {/* Pending gate */}
      {run.pendingGate && (
        <div
          className="flex items-center gap-2 px-5 py-2 flex-shrink-0"
          style={{
            borderBottom: "1px solid rgba(255,255,255,0.07)",
            background: "rgba(124,108,240,0.06)",
          }}
        >
          <span className="font-mono text-[10px] text-[#bab7f6]">
            gate: {run.pendingGate.kind} ({run.pendingGate.stage})
          </span>
          <div className="flex gap-2 ml-auto">
            <button
              aria-label="approve"
              disabled={gate.isPending}
              onClick={() => gate.mutate({ decision: "approve" })}
              className="rounded-[5px] px-2 py-1 text-[10px] text-accent disabled:opacity-40"
              style={{ background: "rgba(124,108,240,0.18)" }}
            >
              Approve
            </button>
            <button
              aria-label="reject"
              disabled={gate.isPending}
              onClick={() => gate.mutate({ decision: "reject" })}
              className="rounded-[5px] px-2 py-1 text-[10px] text-[#c4c5cb] disabled:opacity-40"
              style={{ border: "1px solid rgba(255,255,255,0.12)" }}
            >
              Reject
            </button>
          </div>
        </div>
      )}

      <StepTimeline stages={run.stages} />
      <div className="flex-1 overflow-y-auto">
        <LogStream events={events} />
      </div>
    </div>
  );
}
