import { useState } from "react";
import { useParams } from "react-router-dom";
import { useWorkItem } from "../../lib/api/hooks/useWorkItem";
import { useWorkItemRun } from "../../lib/api/hooks/useWorkItemRun";
import { Breadcrumb } from "./Breadcrumb";
import { ItemHeader } from "./ItemHeader";
import { TabBar } from "./TabBar";
import type { DetailTab } from "./TabBar";

const ALL_DETAIL_TABS: DetailTab[] = ["Spec", "Attachments", "Activity", "Agent", "Subagents"];
import { SpecTab } from "./SpecTab";
import { AgentMonitor } from "./AgentMonitor";

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

  if (isLoading || !item) {
    return <LoadingState />;
  }

  const agentActive = run?.status === "running";

  return (
    <div className="flex flex-col h-full">
      <Breadcrumb item={item} />
      <ItemHeader item={item} />
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
            : <EmptyBody message="No active run" />
        )}
        {activeTab === "Attachments" && <EmptyBody message="No attachments" />}
        {activeTab === "Activity" && <EmptyBody message="No activity yet" />}
        {activeTab === "Subagents" && <EmptyBody message="No subagents" />}
      </div>
    </div>
  );
}
