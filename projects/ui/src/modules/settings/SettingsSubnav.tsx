interface NavItem {
  label: string;
  href: string;
}

interface NavSection {
  sectionLabel: string;
  items: NavItem[];
}

const NAV_SECTIONS: NavSection[] = [
  {
    sectionLabel: "TEAM",
    items: [
      { label: "Agents", href: "/settings/agents" },
      { label: "Budget", href: "/settings/budget" },
      { label: "Secrets", href: "/settings/secrets" },
    ],
  },
];

export function SettingsSubnav({ active }: { active: string }) {
  return (
    <nav
      className="shrink-0 h-full"
      style={{ width: 176, background: "#0a0b0d", padding: "16px 10px" }}
    >
      {NAV_SECTIONS.map((section) => (
        <div key={section.sectionLabel} className="mb-4">
          <p
            className="font-mono font-semibold"
            style={{
              fontSize: 9.5,
              color: "#22252c",
              letterSpacing: "0.08em",
              paddingBottom: 5,
            }}
          >
            {section.sectionLabel}
          </p>
          {section.items.map((item) => {
            const isActive = active === item.href;
            return (
              <a
                key={item.href}
                href={item.href}
                className="block font-medium"
                style={{
                  fontSize: 12,
                  padding: "5px 8px",
                  borderRadius: 5,
                  color: isActive ? "#bab7f6" : "#52555e",
                  background: isActive ? "rgba(124,108,240,0.10)" : "transparent",
                  fontWeight: isActive ? 500 : 400,
                  textDecoration: "none",
                }}
              >
                {item.label}
              </a>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
