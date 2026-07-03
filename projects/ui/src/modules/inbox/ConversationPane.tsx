import { useThread } from "../../lib/api/hooks";
import { Thread } from "../../components/thread";

function TaskBanner({ workItemId, title }: { workItemId: string; title?: string }) {
  return (
    <div
      className="shrink-0 px-4 py-2"
      style={{ borderBottom: "1px solid rgba(255,255,255,0.06)", background: "rgba(124,108,240,0.05)" }}
    >
      <p className="font-mono text-[10px] text-[#7c6cf0]">{workItemId.slice(0, 8)}</p>
      {title && (
        <p className="text-[12px] font-medium text-[#c4c5cb] truncate">{title}</p>
      )}
    </div>
  );
}

interface ConversationPaneProps {
  /** Now carries a work-item id (previously a thread id) */
  threadId: string;
}

export function ConversationPane({ threadId }: ConversationPaneProps) {
  const { data: thread } = useThread(threadId);
  return (
    <Thread
      workItemId={threadId}
      banner={<TaskBanner workItemId={threadId} title={thread?.title} />}
    />
  );
}
