import { PulseDot } from "../../components/ui";

export type DetailTab = "Spec" | "Attachments" | "Activity" | "Agent" | "Thread";


interface TabBarProps {
  tabs: DetailTab[];
  active: DetailTab;
  onSelect: (tab: DetailTab) => void;
  agentActive: boolean;
}

export function TabBar({ tabs, active, onSelect, agentActive }: TabBarProps) {
  return (
    <div
      className="flex items-end gap-[2px] px-[16px]"
      style={{ borderBottom: "1px solid rgba(255,255,255,0.07)" }}
    >
      {tabs.map((tab) => {
        const isActive = tab === active;
        return (
          <button
            key={tab}
            type="button"
            onClick={() => onSelect(tab)}
            className="flex items-center gap-[5px] px-[10px] pb-[8px] pt-[10px] text-[11.5px] font-medium"
            style={{
              color: isActive ? "#bab7f6" : "#42454e",
              borderBottom: isActive
                ? "2px solid #7c6cf0"
                : "2px solid transparent",
              background: "transparent",
              border: "none",
              borderBottomStyle: "solid",
              borderBottomWidth: "2px",
              borderBottomColor: isActive ? "#7c6cf0" : "transparent",
            }}
          >
            {tab}
            {tab === "Agent" && agentActive && <PulseDot size={6} />}
          </button>
        );
      })}
    </div>
  );
}
