import { useState } from "react";
import { useParams } from "react-router-dom";
import { useWorkItem } from "../../lib/api/hooks/useWorkItem";
import { useWorkItemRun } from "../../lib/api/hooks/useWorkItemRun";
import { useCreateModal } from "../create/useCreateModal";
import { Breadcrumb } from "./Breadcrumb";
import { ItemHeader } from "./ItemHeader";
import { TabBar } from "./TabBar";
import type { DetailTab } from "./TabBar";

const ALL_DETAIL_TABS: DetailTab[] = ["Spec", "Attachments", "Activity", "Agent", "Thread"];
import { SpecTab } from "./SpecTab";
import { AgentMonitor } from "./AgentMonitor";
import { AttachmentsPanel } from "./AttachmentsPanel";
import { StartRunButton } from "./StartRunButton";
import { Thread } from "../../components/thread";

function LoadingState() {
  return (
    <div className="flex flex-1 items-center justify-center font-mono text-[11px] text-[#42454e]">
      Loading…
    </div>
  );
}

function EmptyBody({ message }: { message: string }) {
  return (
    <div className="flex flex-1 items-center justify-center font-mono text-[11px] text-[#42454e]">
      {message}
    </div>
  );
}

export function DetailScreen() {
  const { itemId } = useParams<{ itemId: string }>();
  const [activeTab, setActiveTab] = useState<DetailTab>("Spec");

  const { data: item, isLoading } = useWorkItem(itemId ?? "");
  const { data: run } = useWorkItemRun(itemId ?? "");
  const { openEditWorkItem } = useCreateModal();

  if (isLoading || !item) {
    return <LoadingState />;
  }

  const agentActive = run?.status === "running";

  return (
    <div className="flex flex-col h-full">
      <Breadcrumb item={item} />
      <ItemHeader
        item={item}
        onEdit={() => openEditWorkItem(item)}
        actions={<StartRunButton item={item} run={run ?? null} />}
      />
      <TabBar
        tabs={ALL_DETAIL_TABS}
        active={activeTab}
        onSelect={setActiveTab}
        agentActive={agentActive ?? false}
      />
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {activeTab === "Spec" && <SpecTab item={item} />}
        {activeTab === "Agent" && (
          run
            ? <AgentMonitor runId={run.id} />
            : (
              <div className="flex flex-1 flex-col items-center justify-center gap-3">
                <span className="font-mono text-[11px] text-[#42454e]">No active run</span>
                <StartRunButton item={item} run={null} />
              </div>
            )
        )}
        {activeTab === "Attachments" && <AttachmentsPanel workItemId={itemId ?? ""} />}
        {activeTab === "Activity" && <EmptyBody message="No activity yet" />}
        {activeTab === "Thread" && (
          <Thread workItemId={itemId ?? ""} showRail showTyping={agentActive ?? false} />
        )}
      </div>
    </div>
  );
}
