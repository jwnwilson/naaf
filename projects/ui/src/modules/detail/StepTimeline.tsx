import { Fragment } from "react";
import type { components } from "../../lib/api/schema";

type RunStep = components["schemas"]["RunStep"];

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

function StepCircle({ step }: { step: RunStep }) {
  if (step.status === "done") {
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

  if (step.status === "active") {
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
        {step.index + 1}
      </div>
    );
  }

  // pending
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

export function StepTimeline({ steps }: { steps: RunStep[] }) {
  return (
    <div className="flex items-start px-5 py-3.5">
      {steps.map((step, idx) => {
        const prevDone = idx > 0 && steps[idx - 1].status === "done";
        return (
          <Fragment key={step.index}>
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
              <StepCircle step={step} />
              <span
                className="font-mono"
                style={{
                  fontSize: 8.5,
                  color: step.status === "active" ? "#bab7f6" : "#2e3038",
                }}
              >
                {step.label}
              </span>
            </div>
          </Fragment>
        );
      })}
    </div>
  );
}
