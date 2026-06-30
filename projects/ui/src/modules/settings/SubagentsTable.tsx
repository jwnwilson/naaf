import { useState } from "react";
import { Avatar } from "../../components/ui/Avatar";
import { Toggle } from "../../components/ui/Toggle";
import type { AgentDefinition } from "../../lib/api/hooks/useAgentDefinitions";

function roleInitials(role: string): string {
  return role.slice(0, 2).toUpperCase();
}

function AgentRow({ agent }: { agent: AgentDefinition }) {
  const [enabled, setEnabled] = useState(agent.enabled);

  return (
    <div
      className="flex items-center gap-3 px-4"
      style={{ height: 44, borderBottom: "1px solid rgba(255,255,255,0.05)" }}
    >
      <Avatar initials={roleInitials(agent.role)} variant="agent" size={20} />
      <span
        className="flex-1 min-w-0 truncate"
        style={{ fontSize: 12, fontWeight: 500, color: "var(--text-2)" }}
      >
        {agent.role.charAt(0).toUpperCase() + agent.role.slice(1)} Agent
      </span>
      <span
        className="shrink-0 font-mono truncate"
        style={{ width: 160, fontSize: 12, color: "var(--text-3)" }}
      >
        {agent.model}
      </span>
      <span
        className="shrink-0 font-mono text-right"
        style={{ width: 88, fontSize: 12, color: "var(--text-3)" }}
      >
        {agent.tokenLimit.toLocaleString()}
      </span>
      <Toggle checked={enabled} onChange={setEnabled} />
    </div>
  );
}

export function SubagentsTable({ agents }: { agents: AgentDefinition[] }) {
  return (
    <div style={{ background: "#131618", borderRadius: 8, overflow: "hidden" }}>
      {/* Header */}
      <div
        className="flex items-center gap-3 px-4"
        style={{ height: 36, borderBottom: "1px solid rgba(255,255,255,0.07)" }}
      >
        <span style={{ width: 20 }} />
        <span
          className="flex-1 font-mono"
          style={{ fontSize: 10, color: "#52555e", letterSpacing: "0.06em" }}
        >
          NAME
        </span>
        <span
          className="shrink-0 font-mono"
          style={{ width: 160, fontSize: 10, color: "#52555e", letterSpacing: "0.06em" }}
        >
          MODEL
        </span>
        <span
          className="shrink-0 font-mono"
          style={{ width: 88, fontSize: 10, color: "#52555e", letterSpacing: "0.06em" }}
        >
          TOKEN LIMIT
        </span>
        <span
          className="shrink-0 font-mono"
          style={{ fontSize: 10, color: "#52555e", letterSpacing: "0.06em" }}
        >
          ENABLED
        </span>
      </div>

      {/* Rows */}
      {agents.map((agent) => (
        <AgentRow key={agent.id} agent={agent} />
      ))}
    </div>
  );
}
