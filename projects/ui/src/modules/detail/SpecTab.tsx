import ReactMarkdown from "react-markdown";
import { DetailRail } from "./DetailRail";
import type { components } from "../../lib/api/schema";

type WorkItem = components["schemas"]["WorkItem"];

const PROSE_COMPONENTS = {
  h1: ({ children }: { children?: React.ReactNode }) => (
    <h1 className="mb-[12px] text-[15.5px] font-semibold text-[#d8d9de]">{children}</h1>
  ),
  h2: ({ children }: { children?: React.ReactNode }) => (
    <h2 className="mb-[10px] mt-[18px] text-[13.5px] font-semibold text-[#d8d9de]">{children}</h2>
  ),
  p: ({ children }: { children?: React.ReactNode }) => (
    <p className="mb-[10px] text-[13px] leading-[1.72] text-[#8a8d96]">{children}</p>
  ),
  code: ({ children }: { children?: React.ReactNode }) => (
    <code className="rounded-[6px] border border-[rgba(255,255,255,0.06)] bg-[#07080a] px-[6px] py-[2px] font-mono text-[11px] text-[#8a8d96]">
      {children}
    </code>
  ),
  pre: ({ children }: { children?: React.ReactNode }) => (
    <pre className="mb-[12px] overflow-x-auto rounded-[6px] border border-[rgba(255,255,255,0.06)] bg-[#07080a] p-[12px] font-mono text-[11px] text-[#8a8d96]">
      {children}
    </pre>
  ),
  li: ({ children }: { children?: React.ReactNode }) => (
    <li className="mb-[4px] text-[13px] leading-[1.72] text-[#8a8d96]">{children}</li>
  ),
  ul: ({ children }: { children?: React.ReactNode }) => (
    <ul className="mb-[10px] list-disc pl-[20px]">{children}</ul>
  ),
  ol: ({ children }: { children?: React.ReactNode }) => (
    <ol className="mb-[10px] list-decimal pl-[20px]">{children}</ol>
  ),
};

export function SpecTab({ item }: { item: WorkItem }) {
  const spec = item.spec ?? "";

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* Left pane — markdown spec */}
      <div className="flex-1 overflow-y-auto px-[24px] py-[20px]">
        <div className="mb-[10px] flex items-center gap-[8px]">
          <span className="font-mono text-[9.5px] text-[#2e3038]">MARKDOWN SPEC</span>
          <span className="rounded-[3px] border border-[rgba(124,108,240,0.15)] bg-[rgba(124,108,240,0.08)] px-[5px] py-[1px] font-mono text-[9px] text-[#8a86d0]">
            agent-editable
          </span>
        </div>
        <div className="mb-[12px] h-[1px] bg-[rgba(255,255,255,0.05)]" />

        {spec.length === 0 ? (
          <p className="text-[13px] text-[#42454e]">No spec written yet.</p>
        ) : (
          <ReactMarkdown components={PROSE_COMPONENTS}>{spec}</ReactMarkdown>
        )}
      </div>

      {/* Right rail */}
      <DetailRail item={item} />
    </div>
  );
}
