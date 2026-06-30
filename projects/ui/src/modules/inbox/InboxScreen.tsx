import { useNavigate, useParams } from "react-router-dom";
import { useInbox } from "../../lib/api/hooks/useInbox";
import { ConversationPane } from "./ConversationPane";
import { InboxList } from "./InboxList";

export function InboxScreen() {
  const { id } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { data, isLoading } = useInbox();

  const items = data?.results ?? [];
  const selectedId = id ?? items[0]?.id;
  const selectedItem = items.find((item) => item.id === selectedId);

  function handleSelect(itemId: string) {
    navigate(`/inbox/${itemId}`);
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-[12px] text-[#52555e]">Loading…</p>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-[12px] text-[#52555e]">No notifications</p>
      </div>
    );
  }

  return (
    <div className="flex h-full overflow-hidden">
      <InboxList
        selectedId={selectedId}
        onSelect={handleSelect}
      />
      {selectedItem && <ConversationPane item={selectedItem} />}
    </div>
  );
}
