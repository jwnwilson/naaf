import type { components } from "../../lib/api/schema";

type RunEventOut = components["schemas"]["RunEventOut"];

function formatTimestamp(ts: string): string {
  try {
    return new Date(ts).toISOString().slice(11, 19);
  } catch {
    return ts;
  }
}

function lineFor(ev: RunEventOut): string {
  const p = ev.payload as Record<string, unknown>;
  switch (ev.type) {
    case "log":
      return String(p.message ?? "");
    case "stage_started":
      return `▶ ${ev.stage} started`;
    case "stage_passed":
      return `✓ ${ev.stage} (${Number(p.tokens ?? 0)} tok)`;
    case "stage_failed":
      return `✕ ${ev.stage} failed`;
    case "gate_requested":
      return `⏸ gate: ${String(p.kind ?? "")}`;
    case "gate_resolved":
      return `▶ gate ${String(p.decision ?? "")}`;
    case "run_started":
      return "▶ run started";
    case "run_finished":
      return `■ run ${String(p.status ?? "finished")}`;
    default:
      return ev.type;
  }
}

function LogEntry({ ev }: { ev: RunEventOut }) {
  return (
    <div className="flex gap-2 items-baseline">
      <span className="flex-shrink-0" style={{ color: "#28292e" }}>
        {formatTimestamp(ev.createdAt)}
      </span>
      {ev.stage && <span style={{ color: "#6b6e76" }}>{ev.stage}</span>}
      <span style={{ color: "#42454e" }}>{lineFor(ev)}</span>
    </div>
  );
}

export function LogStream({ events }: { events: RunEventOut[] }) {
  return (
    <div className="flex flex-col gap-1 px-5 py-3 font-mono text-[10.5px] overflow-y-auto">
      {events.map((ev) => (
        <LogEntry key={ev.id} ev={ev} />
      ))}
    </div>
  );
}
