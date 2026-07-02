import { Fragment } from "react";
import type { components } from "../../lib/api/schema";

type StageStateOut = components["schemas"]["StageStateOut"];

type Circle = "done" | "active" | "failed" | "pending";

function circle(status: string): Circle {
  if (status === "passed") return "done";
  if (status === "running" || status === "gated") return "active";
  if (status === "failed") return "failed";
  return "pending"; // pending, skipped
}

const CHECK_ICON = (
  <svg width="9" height="9" viewBox="0 0 9 9" fill="none" aria-hidden="true">
    <path
      d="M1.5 4.5l2 2L7.5 2"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

function StageCircle({ state, index }: { state: Circle; index: number }) {
  if (state === "done") {
    return (
      <div
        className="flex items-center justify-center text-[#8a8d96]"
        style={{
          width: 20,
          height: 20,
          borderRadius: "50%",
          background: "#1e2028",
          border: "1.5px solid #36393f",
        }}
      >
        {CHECK_ICON}
      </div>
    );
  }

  if (state === "active") {
    return (
      <div
        className="flex items-center justify-center font-mono text-[#bab7f6] animate-[pulse_2s_infinite]"
        style={{
          width: 22,
          height: 22,
          borderRadius: "50%",
          background: "rgba(124,108,240,0.15)",
          border: "2px solid #7c6cf0",
          fontSize: 8,
        }}
      >
        {index + 1}
      </div>
    );
  }

  if (state === "failed") {
    return (
      <div
        className="flex items-center justify-center font-mono text-[#f0a0a0]"
        style={{
          width: 20,
          height: 20,
          borderRadius: "50%",
          background: "rgba(240,120,120,0.12)",
          border: "1.5px solid #7a3a3a",
          fontSize: 9,
        }}
      >
        ✕
      </div>
    );
  }

  return (
    <div
      style={{
        width: 20,
        height: 20,
        borderRadius: "50%",
        background: "#0f1012",
        border: "1.5px solid #1a1c22",
      }}
    />
  );
}

export function StepTimeline({ stages }: { stages: StageStateOut[] }) {
  return (
    <div className="flex items-start px-5 py-3.5">
      {stages.map((s, idx) => {
        const state = circle(s.status);
        const prevDone = idx > 0 && circle(stages[idx - 1].status) === "done";
        return (
          <Fragment key={`${s.stage}-${idx}`}>
            {idx > 0 && (
              <div
                className="flex-1"
                style={{
                  height: 1.5,
                  marginTop: 10,
                  background: prevDone ? "#7c6cf0" : "#1e2028",
                }}
              />
            )}
            <div className="flex flex-col items-center" style={{ gap: 4 }}>
              <StageCircle state={state} index={idx} />
              <span
                className="font-mono"
                style={{
                  fontSize: 8.5,
                  color: state === "active" ? "#bab7f6" : "#2e3038",
                }}
              >
                {s.stage}
              </span>
            </div>
          </Fragment>
        );
      })}
    </div>
  );
}
