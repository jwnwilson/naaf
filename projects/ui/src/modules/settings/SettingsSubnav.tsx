import { Link } from "react-router-dom";

interface NavItem {
  label: string;
  href: string;
  isRoute?: boolean;
}

interface NavSection {
  sectionLabel: string;
  items: NavItem[];
}

const NAV_SECTIONS: NavSection[] = [
  {
    sectionLabel: "TEAM",
    items: [
      { label: "Agents", href: "/settings/agents", isRoute: true },
      { label: "Budget", href: "/settings/budget", isRoute: false },
      { label: "Secrets", href: "/settings/secrets", isRoute: false },
    ],
  },
];

const itemStyle = (isActive: boolean) => ({
  fontSize: 12,
  padding: "5px 8px",
  borderRadius: 5,
  color: isActive ? "#bab7f6" : "#52555e",
  background: isActive ? "rgba(124,108,240,0.10)" : "transparent",
  fontWeight: isActive ? 500 : 400,
  textDecoration: "none",
});

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
            const baseStyle = { ...itemStyle(isActive), display: "block" };

            if (item.isRoute) {
              return (
                <Link
                  key={item.href}
                  to={item.href}
                  className="font-medium"
                  style={baseStyle}
                >
                  {item.label}
                </Link>
              );
            }

            return (
              <span
                key={item.href}
                className="block font-medium"
                style={baseStyle}
              >
                {item.label}
              </span>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
