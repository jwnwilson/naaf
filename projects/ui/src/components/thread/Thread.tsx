import { useEffect, useRef, type ReactNode } from "react";
import { useAnswerQuestion, useThreadMessages } from "../../lib/api/hooks";
import { useAgentActivity } from "../../lib/api/hooks/useAgentActivity";
import { MessageItem } from "./MessageItem";
import { ThreadComposer } from "./ThreadComposer";
import { ThreadRail } from "./ThreadRail";
import { groupMessagesByDay } from "./groupByDay";
import { ActivityFeedView } from "./ActivityFeed";
import { isNearBottom } from "./autoscroll";

interface ThreadProps {
  workItemId: string;
  showRail?: boolean;
  /** Documented no-op / tight-padding hint */
  compact?: boolean;
  banner?: ReactNode;
  composerPlaceholder?: string;
}

function DayDivider({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2.5 py-1.5">
      <div className="flex-1 h-px bg-[rgba(255,255,255,0.05)]" />
      <span className="font-mono text-[10px] text-[#2e3038]">{label}</span>
      <div className="flex-1 h-px bg-[rgba(255,255,255,0.05)]" />
    </div>
  );
}

export function Thread({
  workItemId,
  showRail,
  banner,
  composerPlaceholder,
}: ThreadProps) {
  const activity = useAgentActivity({ threadId: workItemId });
  const { data: messages = [], isLoading } = useThreadMessages(workItemId, activity.isWorking);
  const answer = useAnswerQuestion(workItemId);
  const handleAnswer = (msgId: string, option: string) => { answer.mutate({ msgId, option }); };
  const groups = groupMessagesByDay(messages);

  const scrollRef = useRef<HTMLDivElement>(null);
  const atBottomRef = useRef(true);

  const handleScroll = () => {
    const el = scrollRef.current;
    if (el) atBottomRef.current = isNearBottom(el);
  };

  // Switching threads always lands at the bottom. Declared BEFORE the follow
  // effect so atBottomRef is true when it runs on the same workItemId change.
  useEffect(() => {
    atBottomRef.current = true;
  }, [workItemId]);

  // Follow new messages / streaming activity while pinned near the bottom.
  useEffect(() => {
    const el = scrollRef.current;
    if (el && atBottomRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [
    workItemId,
    messages.length,
    activity.textBlocks.length,
    activity.toolCalls.length,
    activity.isWorking,
  ]);

  return (
    <div className="flex flex-col h-full flex-1 overflow-hidden">
      {banner}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        <div className="flex flex-col flex-1 overflow-hidden">
          <div
            ref={scrollRef}
            onScroll={handleScroll}
            className="flex-1 overflow-y-auto px-4 py-4"
          >
            {isLoading && (
              <p className="text-[11px] text-[#30333c]">Loading…</p>
            )}
            {!isLoading && messages.length === 0 && !activity.isWorking && (
              <p className="text-[11px] text-[#30333c]">No messages yet</p>
            )}
            {groups.map((group) => (
              <div key={group.key}>
                {group.label && <DayDivider label={group.label} />}
                {group.messages.map((msg) => (
                  <MessageItem key={msg.id} message={msg} onAnswer={handleAnswer} answering={answer.isPending} />
                ))}
              </div>
            ))}
            <ActivityFeedView
              isWorking={activity.isWorking}
              textBlocks={activity.textBlocks}
              toolCalls={activity.toolCalls}
            />
          </div>
          <ThreadComposer
            workItemId={workItemId}
            placeholder={composerPlaceholder}
          />
        </div>
        {showRail && <ThreadRail workItemId={workItemId} />}
      </div>
    </div>
  );
}
