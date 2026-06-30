import { Avatar } from "../../components/ui/Avatar";
import { Card } from "../../components/ui/Card";
import type { AgentDefinition } from "../../lib/api/hooks/useAgentDefinitions";

const FIELD_STYLE: React.CSSProperties = {
  padding: "7px 10px",
  background: "#0e0f11",
  border: "1px solid rgba(255,255,255,0.09)",
  borderRadius: 5,
  fontSize: 12,
  fontFamily: "monospace",
  color: "#c4c5cb",
  width: "100%",
};

function roleInitials(role: string): string {
  return role.slice(0, 2).toUpperCase();
}

function ActiveBadge() {
  return (
    <span
      className="inline-flex items-center rounded-[3px] border font-mono font-semibold tracking-[0.03em]"
      style={{
        fontSize: 8.5,
        padding: "2px 5px",
        background: "rgba(124,108,240,0.12)",
        borderColor: "rgba(124,108,240,0.25)",
        color: "#bab7f6",
      }}
    >
      ACTIVE
    </span>
  );
}

export function LeadAgentCard({ agent }: { agent: AgentDefinition }) {
  return (
    <Card>
      <div style={{ background: "#131618", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 8, padding: 16 }}>
        {/* Header */}
        <div className="flex items-center gap-3 mb-4">
          <Avatar initials={roleInitials(agent.role)} variant="agent" size={26} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-1)" }}>
                {agent.role.charAt(0).toUpperCase() + agent.role.slice(1)} Agent
              </span>
              <ActiveBadge />
            </div>
            <p style={{ fontSize: 11, color: "var(--text-3)", marginTop: 1 }}>
              Team lead orchestrator
            </p>
          </div>
        </div>

        {/* 2-col grid: model + token limit */}
        <div className="grid grid-cols-2 gap-3 mb-3">
          <div>
            <label
              className="block font-mono"
              style={{ fontSize: 10, color: "#52555e", marginBottom: 4 }}
            >
              MODEL
            </label>
            <input
              readOnly
              value={agent.model}
              style={FIELD_STYLE}
            />
          </div>
          <div>
            <label
              className="block font-mono"
              style={{ fontSize: 10, color: "#52555e", marginBottom: 4 }}
            >
              TOKEN LIMIT
            </label>
            <input
              readOnly
              value={agent.tokenLimit.toLocaleString()}
              style={FIELD_STYLE}
            />
          </div>
        </div>

        {/* System prompt */}
        <div>
          <label
            className="block font-mono"
            style={{ fontSize: 10, color: "#52555e", marginBottom: 4 }}
          >
            SYSTEM PROMPT
          </label>
          <textarea
            readOnly
            value={agent.systemPrompt ?? ""}
            rows={4}
            style={{ ...FIELD_STYLE, resize: "none" }}
          />
        </div>
      </div>
    </Card>
  );
}
