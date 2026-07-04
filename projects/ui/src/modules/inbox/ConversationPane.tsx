import { Link } from "react-router-dom";
import { useThread } from "../../lib/api/hooks";
import { Thread } from "../../components/thread";

interface TaskBannerProps {
  workItemId: string;
  projectId?: string;
  title?: string;
}

function bannerHref({ workItemId, projectId }: TaskBannerProps): string | null {
  if (!projectId) return null;
  return workItemId
    ? `/projects/${projectId}/items/${workItemId}`
    : `/projects?project=${projectId}`;
}

function TaskBanner({ workItemId, projectId, title }: TaskBannerProps) {
  const href = bannerHref({ workItemId, projectId });
  const label = title ?? workItemId.slice(0, 8);
  return (
    <div
      className="shrink-0 px-4 py-2"
      style={{ borderBottom: "1px solid rgba(255,255,255,0.06)", background: "rgba(124,108,240,0.05)" }}
    >
      {href ? (
        <Link
          to={href}
          className="text-[12px] font-medium text-[#c4c5cb] truncate hover:text-[#7c6cf0] hover:underline"
        >
          {label}
        </Link>
      ) : (
        <p className="text-[12px] font-medium text-[#c4c5cb] truncate">{label}</p>
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
      banner={
        <TaskBanner
          workItemId={thread?.workItemId ?? threadId}
          projectId={thread?.projectId}
          title={thread?.title}
        />
      }
    />
  );
}
