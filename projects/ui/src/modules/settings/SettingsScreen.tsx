import { useLocation } from "react-router-dom";
import { useAgentDefinitions } from "../../lib/api/hooks/useAgentDefinitions";
import { SettingsSubnav } from "./SettingsSubnav";
import { LeadAgentCard } from "./LeadAgentCard";
import { SubagentsTable } from "./SubagentsTable";

export function SettingsScreen() {
  const { pathname } = useLocation();
  const { data: agents, isLoading, isError } = useAgentDefinitions();

  const leadAgent = agents?.find((a) => a.role === "lead") ?? agents?.[0];
  const subAgents = agents?.filter((a) => a !== leadAgent) ?? [];

  return (
    <div className="flex h-full">
      <SettingsSubnav active={pathname} />

      <div className="flex-1 overflow-y-auto p-6 flex flex-col gap-6">
        <h2 style={{ fontSize: 15, fontWeight: 600, color: "var(--text-1)", marginBottom: 4 }}>
          Agents
        </h2>

        {isLoading && (
          <p style={{ fontSize: 12, color: "var(--text-3)" }}>Loading…</p>
        )}

        {isError && (
          <p style={{ fontSize: 12, color: "#b05848" }}>Failed to load agent definitions.</p>
        )}

        {leadAgent && <LeadAgentCard agent={leadAgent} />}

        {subAgents.length > 0 && (
          <div>
            <p
              className="font-mono font-semibold mb-3"
              style={{ fontSize: 10, color: "#52555e", letterSpacing: "0.08em" }}
            >
              SUB-AGENTS
            </p>
            <SubagentsTable agents={subAgents} />
          </div>
        )}
      </div>
    </div>
  );
}
