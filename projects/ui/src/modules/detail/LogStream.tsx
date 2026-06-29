import type { components } from "../../lib/api/schema";

type LogLine = components["schemas"]["LogLine"];

function formatTimestamp(ts: string): string {
  try {
    return new Date(ts).toISOString().slice(11, 19);
  } catch {
    return ts;
  }
}

function isFilePath(target: string): boolean {
  return target.includes("/") || target.includes(".");
}

function LogEntry({ line }: { line: LogLine }) {
  const isToolLine = line.type === "tool_call" || line.type === "result";

  return (
    <div className="flex gap-2 items-baseline">
      <span className="flex-shrink-0" style={{ color: "#28292e" }}>
        {formatTimestamp(line.timestamp)}
      </span>

      {isToolLine ? (
        <>
          {line.tool && (
            <span style={{ color: "#6b6e76" }}>{line.tool}</span>
          )}
          {line.target && (
            <span style={{ color: isFilePath(line.target) ? "#7c6cf0" : "#6b6e76" }}>
              {line.target}
            </span>
          )}
          {line.message && (
            <span style={{ color: "#42454e" }}>{line.message}</span>
          )}
        </>
      ) : (
        <span style={{ color: "#42454e" }}>{line.message}</span>
      )}
    </div>
  );
}

export function LogStream({ lines }: { lines: LogLine[] }) {
  if (lines.length === 0) {
    return (
      <div
        className="font-mono text-[11px] px-3 py-3"
        style={{
          background: "#07080a",
          borderRadius: 6,
          color: "#42454e",
          lineHeight: 1.8,
        }}
      >
        No log output yet.
      </div>
    );
  }

  return (
    <div
      className="font-mono text-[11px] overflow-y-auto"
      style={{
        background: "#07080a",
        borderRadius: 6,
        lineHeight: 1.8,
      }}
    >
      <div className="px-3 py-2">
        {lines.map((line, idx) => (
          <LogEntry key={idx} line={line} />
        ))}
      </div>
    </div>
  );
}
