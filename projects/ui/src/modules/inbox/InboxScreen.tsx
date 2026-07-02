import { useNavigate, useParams } from "react-router-dom";
import { useThreads } from "../../lib/api/hooks";
import { ConversationPane } from "./ConversationPane";
import { InboxList } from "./InboxList";

export function InboxScreen() {
  const { id } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { data: threads = [], isLoading } = useThreads();

  const selectedId = id ?? threads[0]?.id;

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-[12px] text-[#52555e]">Loading…</p>
      </div>
    );
  }

  if (threads.length === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-[12px] text-[#52555e]">No conversations</p>
      </div>
    );
  }

  return (
    <div className="flex h-full overflow-hidden">
      <InboxList selectedId={selectedId} onSelect={(tid) => navigate(`/inbox/${tid}`)} />
      {selectedId && <ConversationPane threadId={selectedId} />}
    </div>
  );
}
