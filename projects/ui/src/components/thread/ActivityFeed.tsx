import { useAgentActivity, type ActivityState } from "../../lib/api/hooks/useAgentActivity";
import { TypingIndicator } from "../ui/TypingIndicator";

export function ActivityFeedView({
  isWorking,
  textBlocks,
  toolCalls,
}: Pick<ActivityState, "isWorking" | "textBlocks" | "toolCalls">) {
  if (!isWorking) return null;
  const hasContent = textBlocks.length > 0 || toolCalls.length > 0;
  return (
    <div className="flex gap-2.5 items-start mb-3.5" data-testid="activity-feed">
      <div className="w-[26px] h-[26px] flex-none" />
      <div
        className="flex flex-col gap-1 px-3.5 py-2.5"
        style={{ background: "#131618", border: "1px solid rgba(255,255,255,0.07)", borderRadius: "3px 10px 10px 10px" }}
      >
        {textBlocks.map((t, i) => (
          <p key={`t${i}`} className="text-[12px] text-[#c4c5cb] whitespace-pre-wrap">{t}</p>
        ))}
        {toolCalls.map((c, i) => (
          <p key={`c${i}`} className="font-mono text-[10px] text-[#7c6cf0]">
            🔧 {c.name}{c.result ? ` → ${c.result.slice(0, 40)}` : "…"}
          </p>
        ))}
        {!hasContent && <div data-testid="activity-typing"><TypingIndicator /></div>}
      </div>
    </div>
  );
}

export function ActivityFeed({ scope }: { scope: { threadId?: string; runId?: string } }) {
  const { isWorking, textBlocks, toolCalls } = useAgentActivity(scope);
  return <ActivityFeedView isWorking={isWorking} textBlocks={textBlocks} toolCalls={toolCalls} />;
}
