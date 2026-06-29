# A2 Foundation — Scaffold + Design System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the `projects/ui/` Vite/React/TS/Tailwind workspace and build the token-driven design-system primitives + icon set the rest of the NAAF UI is composed from.

**Architecture:** A pnpm-managed Vite SPA. Design tokens from the handoff live as CSS variables in `lib/theme/tokens.css`; Tailwind v4 consumes them via `@theme` so components use semantic utility classes (`bg-bg-base`, `text-text-2`, `border-border`, `text-accent`). Each primitive is a small, presentational, prop-driven component in `components/ui/`, tested with vitest + React Testing Library. No data layer, no app shell, no screens yet — those are later plans.

**Tech Stack:** pnpm, Vite 5, React 18, TypeScript 5, Tailwind CSS v4, vitest + @testing-library/react + jsdom, eslint.

## Global Constraints

- Package manager is **pnpm** (never npm). All commands run from `projects/ui/`.
- This is the **first A2 plan**; later plans (data layer, shell, screens) build on it. Do NOT build screens, routing, or the data layer here.
- **The authoritative source for every exact value** (colors, font sizes, spacing, radii, SVG math, component anatomy) is `docs/design/README.md` (relative to repo root). Tasks cite the section; read it for the exact value rather than guessing. `docs/design/NAAF Hi-Fi.dc.html` holds the exact inline SVG path data for icons and status circles.
- Components are **presentational and prop-driven** — no API types, no fetching, no global state.
- Design tokens are referenced via the Tailwind theme / CSS variables, never hard-coded hex in components (except where a one-off arbitrary value like `text-[11.5px]` is unavoidable).
- TypeScript strict mode; no `any` in component props.
- Commit format `<type>: <description>`; one focused commit per task.
- TDD: write the failing test first, run it (fail), implement, run it (pass), commit. Tests assert behavior/output, not snapshots.
- Gates after each task: `pnpm test` green; `pnpm lint` (eslint + `tsc --noEmit`) clean.
- Work happens in the `feat/a2-ui` worktree at `.worktrees/a2-ui`.

---

## File Structure

```
projects/ui/
  package.json · pnpm-lock.yaml · vite.config.ts · tsconfig.json · tsconfig.node.json
  .eslintrc.cjs · index.html · postcss.config.js
  src/
    main.tsx                      # minimal entry (renders a placeholder; real app shell is a later plan)
    index.css                     # imports tokens.css + Tailwind
    lib/theme/tokens.css          # design tokens as CSS variables + @theme mapping + keyframes
    components/ui/
      icons/                      # ~14 inline-SVG icon components + index.ts
      StatusCircle.tsx · PriorityBars.tsx · PulseDot.tsx
      Avatar.tsx · Tag.tsx · StatusBadge.tsx
      Button.tsx · Chip.tsx · Toggle.tsx
      ProgressBar.tsx · Card.tsx · MetricCard.tsx · TypingIndicator.tsx
    test/setup.ts                 # vitest + RTL + jest-dom
```

Each primitive is its own file (one responsibility), with a co-located `*.test.tsx`.

---

### Task 1: Scaffold the `projects/ui` Vite workspace + tokens

**Files:**
- Create: `projects/ui/package.json`, `vite.config.ts`, `tsconfig.json`, `tsconfig.node.json`, `.eslintrc.cjs`, `postcss.config.js`, `index.html`, `src/main.tsx`, `src/index.css`, `src/lib/theme/tokens.css`, `src/test/setup.ts`
- Test: `projects/ui/src/lib/theme/tokens.test.ts`

**Interfaces:**
- Produces: a working pnpm workspace where `pnpm test`, `pnpm lint`, and `pnpm build` run; Tailwind utilities backed by design tokens (`bg-bg-base`, `text-text-1`..`text-text-7`, `text-accent`, `border-border`, etc.); the `pulse` keyframe animation. Later plans add `app/`, `modules/`, `lib/api/`.

- [ ] **Step 1: Write the failing test**

`projects/ui/src/lib/theme/tokens.test.ts`:
```ts
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(resolve(__dirname, "tokens.css"), "utf8");

describe("design tokens", () => {
  it("defines the core background, text, accent, and border tokens", () => {
    for (const token of [
      "--bg-base", "--bg-sidebar", "--bg-surface",
      "--text-1", "--text-4", "--text-7",
      "--accent", "--accent-bg", "--border", "--border-strong",
      "--green", "--red-text", "--yellow-text", "--blue-text",
    ]) {
      expect(css).toContain(token);
    }
  });

  it("uses the exact accent violet from the handoff", () => {
    expect(css).toMatch(/--accent:\s*#7c6cf0/);
  });

  it("defines the pulse keyframes", () => {
    expect(css).toContain("@keyframes pulse");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm test` — but pnpm isn't set up yet, so this step is reached only after Steps 3–5 create the scaffold. Order note: create the scaffold files (Steps 3–6) FIRST, write `tokens.css` minimal/empty so the test FAILS (missing tokens), confirm fail, then fill tokens to pass. Practically: do Step 3–6, then create `tokens.css` empty, run `pnpm test` → FAIL, then Step 7 fills it → PASS.

- [ ] **Step 3: Create package.json**

`projects/ui/package.json`:
```json
{
  "name": "naaf-ui",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "lint": "eslint . && tsc --noEmit",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@tailwindcss/vite": "^4.0.0",
    "@testing-library/jest-dom": "^6.4.0",
    "@testing-library/react": "^16.0.0",
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "eslint": "^9.0.0",
    "eslint-plugin-react-hooks": "^5.0.0",
    "eslint-plugin-react-refresh": "^0.4.0",
    "jsdom": "^25.0.0",
    "tailwindcss": "^4.0.0",
    "typescript": "^5.5.0",
    "typescript-eslint": "^8.0.0",
    "vite": "^5.4.0",
    "vitest": "^2.1.0"
  }
}
```

- [ ] **Step 4: Create the Vite + TS + Tailwind config**

`projects/ui/vite.config.ts`:
```ts
/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
    css: true,
  },
});
```

`projects/ui/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "skipLibCheck": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

`projects/ui/tsconfig.node.json`:
```json
{
  "compilerOptions": {
    "composite": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true
  },
  "include": ["vite.config.ts"]
}
```

`projects/ui/postcss.config.js`:
```js
export default {};
```
(Tailwind v4 runs through the Vite plugin, so PostCSS needs no Tailwind entry; keep the file empty/minimal.)

`projects/ui/.eslintrc.cjs`:
```cjs
module.exports = {
  root: true,
  env: { browser: true, es2022: true },
  extends: ["eslint:recommended"],
  parser: "@typescript-eslint/parser",
  plugins: ["@typescript-eslint", "react-hooks", "react-refresh"],
  settings: { react: { version: "18" } },
  ignorePatterns: ["dist", "node_modules"],
  rules: {},
};
```

- [ ] **Step 5: Create the HTML entry, main, and CSS**

`projects/ui/index.html`:
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>NAAF</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`projects/ui/src/main.tsx`:
```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <div className="min-h-screen bg-bg-base text-text-1">NAAF UI</div>
  </StrictMode>,
);
```

`projects/ui/src/index.css`:
```css
@import "./lib/theme/tokens.css";
@import "tailwindcss";
```

`projects/ui/src/test/setup.ts`:
```ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 6: Install deps and confirm the failing test**

Run: `cd projects/ui && pnpm install`
Create `src/lib/theme/tokens.css` as an empty file, then run `pnpm test`
Expected: FAIL — `tokens.test.ts` cannot find the tokens.

- [ ] **Step 7: Fill in tokens.css**

`projects/ui/src/lib/theme/tokens.css` — transcribe the EXACT values from `docs/design/README.md` § "Design Tokens" (Colours). Structure:
```css
:root {
  /* Backgrounds */
  --bg-base: #0e0f11;
  --bg-sidebar: #080a0d;
  --bg-surface: #131618;
  --bg-surface-2: #0a0b0d;
  --bg-input: #101316;
  --bg-overlay: #1a1c22;
  --bg-inset: #07080a;
  /* Text */
  --text-1: #e2e3e8;
  --text-2: #c4c5cb;
  --text-3: #8a8d96;
  --text-4: #52555e;
  --text-5: #42454e;
  --text-6: #30333c;
  --text-7: #22252c;
  /* Borders */
  --border-subtle: rgba(255,255,255,0.055);
  --border: rgba(255,255,255,0.07);
  --border-strong: rgba(255,255,255,0.09);
  /* Accent */
  --accent: #7c6cf0;
  --accent-bg: rgba(124,108,240,0.10);
  --accent-bg-hover: rgba(124,108,240,0.14);
  --accent-border: rgba(124,108,240,0.25);
  --accent-text: #bab7f6;
  /* Semantic */
  --green: #4a8c68;
  --green-bg: rgba(74,140,104,0.10);
  --red-text: #b05848;
  --red-border: rgba(180,60,60,0.20);
  --yellow-text: #907030;
  --blue-text: #4868a0;
}

/* Map tokens into the Tailwind v4 theme so utilities like bg-bg-base,
   text-text-2, border-border, text-accent, bg-accent-bg are generated. */
@theme inline {
  --color-bg-base: var(--bg-base);
  --color-bg-sidebar: var(--bg-sidebar);
  --color-bg-surface: var(--bg-surface);
  --color-bg-surface-2: var(--bg-surface-2);
  --color-bg-input: var(--bg-input);
  --color-bg-overlay: var(--bg-overlay);
  --color-bg-inset: var(--bg-inset);
  --color-text-1: var(--text-1);
  --color-text-2: var(--text-2);
  --color-text-3: var(--text-3);
  --color-text-4: var(--text-4);
  --color-text-5: var(--text-5);
  --color-text-6: var(--text-6);
  --color-text-7: var(--text-7);
  --color-border: var(--border);
  --color-border-subtle: var(--border-subtle);
  --color-border-strong: var(--border-strong);
  --color-accent: var(--accent);
  --color-accent-bg: var(--accent-bg);
  --color-accent-bg-hover: var(--accent-bg-hover);
  --color-accent-border: var(--accent-border);
  --color-accent-text: var(--accent-text);
  --color-green: var(--green);
  --color-green-bg: var(--green-bg);
  --color-red-text: var(--red-text);
  --color-red-border: var(--red-border);
  --color-yellow-text: var(--yellow-text);
  --color-blue-text: var(--blue-text);
  --font-mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50%      { opacity: 0.3; }
}
```

- [ ] **Step 8: Run test + lint + build**

Run: `cd projects/ui && pnpm test && pnpm lint && pnpm build`
Expected: tokens tests PASS; eslint + tsc clean; vite build produces `dist/`.

- [ ] **Step 9: Commit**

```bash
git add projects/ui
git commit -m "chore: scaffold projects/ui (vite/react/ts/tailwind) + design tokens"
```

---

### Task 2: Icon set

**Files:**
- Create: `projects/ui/src/components/ui/icons/` — one file per icon + `index.ts`
- Test: `projects/ui/src/components/ui/icons/icons.test.tsx`

**Interfaces:**
- Consumes: nothing (pure SVG).
- Produces: ~14 icon components, each `({ size = 13, className }: IconProps) => JSX.Element`, rendering an inline `<svg>` that uses `currentColor` for stroke/fill so colour is inherited. `IconProps = { size?: number; className?: string }`. Exported from `icons/index.ts`. Icon list (from `docs/design/README.md` § Icons): `DashboardIcon, InboxIcon, ProjectsIcon, AgentsIcon, SettingsIcon, SearchIcon, GitRepoIcon, ListIcon, GridIcon, PlusIcon, ChevronDownIcon, ChevronRightIcon, CheckIcon, DocumentIcon`.

- [ ] **Step 1: Write the failing test**

`projects/ui/src/components/ui/icons/icons.test.tsx`:
```tsx
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import * as Icons from "./index";

describe("icon set", () => {
  const names = [
    "DashboardIcon", "InboxIcon", "ProjectsIcon", "AgentsIcon", "SettingsIcon",
    "SearchIcon", "GitRepoIcon", "ListIcon", "GridIcon", "PlusIcon",
    "ChevronDownIcon", "ChevronRightIcon", "CheckIcon", "DocumentIcon",
  ] as const;

  it("exports every named icon", () => {
    for (const name of names) expect(Icons[name as keyof typeof Icons]).toBeTypeOf("function");
  });

  it("renders an svg that inherits colour via currentColor and respects size", () => {
    const { container } = render(<Icons.PlusIcon size={20} />);
    const svg = container.querySelector("svg")!;
    expect(svg).toBeInTheDocument();
    expect(svg.getAttribute("width")).toBe("20");
    expect(container.innerHTML).toContain("currentColor");
  });

  it("applies className to the svg", () => {
    const { container } = render(<Icons.CheckIcon className="text-accent" />);
    expect(container.querySelector("svg")!.getAttribute("class")).toContain("text-accent");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd projects/ui && pnpm test src/components/ui/icons`
Expected: FAIL — `./index` not found.

- [ ] **Step 3: Implement the icons**

Create `projects/ui/src/components/ui/icons/types.ts`:
```ts
export type IconProps = { size?: number; className?: string };
```

For each icon create a file (e.g. `PlusIcon.tsx`) following this exact pattern — extract the precise `<path>`/`<circle>` geometry for each icon from `docs/design/NAAF Hi-Fi.dc.html` (the README § Icons says each icon's SVG source is in the reference file; icons are 11–13px and use `currentColor`):
```tsx
import type { IconProps } from "./types";

export function PlusIcon({ size = 13, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 13 13" fill="none" className={className}>
      <path d="M6.5 2.5v8M2.5 6.5h8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}
```
Repeat for all 14 icons, copying each icon's exact geometry from the hi-fi HTML. Keep `currentColor`, set `viewBox` to the icon's native box, and keep stroke widths from the source. `index.ts` re-exports them:
```ts
export * from "./types";
export { DashboardIcon } from "./DashboardIcon";
export { InboxIcon } from "./InboxIcon";
// …one line per icon…
export { DocumentIcon } from "./DocumentIcon";
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd projects/ui && pnpm test src/components/ui/icons`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/components/ui/icons
git commit -m "feat(ui): inline SVG icon set"
```

---

### Task 3: Status visuals — StatusCircle, PriorityBars, PulseDot

**Files:**
- Create: `projects/ui/src/components/ui/StatusCircle.tsx`, `PriorityBars.tsx`, `PulseDot.tsx`
- Test: `projects/ui/src/components/ui/StatusCircle.test.tsx`, `PriorityBars.test.tsx`, `PulseDot.test.tsx`

**Interfaces:**
- Produces:
  - `WorkItemStatus = "backlog" | "todo" | "in_progress" | "in_review" | "done"` (exported from `StatusCircle.tsx` for now; the data layer plan will re-home it).
  - `StatusCircle({ status, size = 13 }: { status: WorkItemStatus; size?: number })` — renders the SVG circle variant per `docs/design/README.md` § "Status Circles (SVG, 13×13)". Use the exact geometry: r=4.5, circumference ≈ 28.27, half-dash 14.14, three-quarter 21.2; the documented stroke colours and dash arrays per status; `done` renders the filled circle + check path.
  - `PriorityBars({ priority }: { priority: "low" | "medium" | "high" | "urgent" })` — 3 stepped vertical bars (heights 4/7/10px, width 3px), filled grey `#4a4d56` up to the level and faint `#25272e` above (per § "List rows" Priority bars).
  - `PulseDot({ size = 6, className }: { size?: number; className?: string })` — a filled accent dot with the running-agent glow + `animation: pulse 2s infinite` (per § Animation). Uses inline style for the box-shadow glow and `animate-[pulse_2s_infinite]`.

- [ ] **Step 1: Write the failing tests**

`projects/ui/src/components/ui/StatusCircle.test.tsx`:
```tsx
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusCircle } from "./StatusCircle";

describe("StatusCircle", () => {
  it("renders an svg sized to the prop", () => {
    const { container } = render(<StatusCircle status="todo" size={13} />);
    const svg = container.querySelector("svg")!;
    expect(svg.getAttribute("width")).toBe("13");
  });

  it("renders the done variant with a check path", () => {
    const { container } = render(<StatusCircle status="done" />);
    expect(container.querySelector("path")).toBeInTheDocument();
  });

  it("uses an accent arc for in_progress", () => {
    const { container } = render(<StatusCircle status="in_progress" />);
    expect(container.innerHTML.toLowerCase()).toContain("#7c6cf0");
  });
});
```

`projects/ui/src/components/ui/PriorityBars.test.tsx`:
```tsx
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PriorityBars } from "./PriorityBars";

describe("PriorityBars", () => {
  it("always renders three bars", () => {
    const { container } = render(<PriorityBars priority="medium" />);
    expect(container.querySelectorAll("[data-bar]")).toHaveLength(3);
  });

  it("fills more bars for higher priority", () => {
    const { container: low } = render(<PriorityBars priority="low" />);
    const { container: urgent } = render(<PriorityBars priority="urgent" />);
    const filled = (c: HTMLElement) =>
      [...c.querySelectorAll("[data-bar]")].filter((b) => b.getAttribute("data-filled") === "true").length;
    expect(filled(urgent.firstChild as HTMLElement)).toBeGreaterThan(filled(low.firstChild as HTMLElement));
  });
});
```

`projects/ui/src/components/ui/PulseDot.test.tsx`:
```tsx
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PulseDot } from "./PulseDot";

describe("PulseDot", () => {
  it("renders a sized element with the pulse animation", () => {
    const { container } = render(<PulseDot size={6} />);
    const el = container.firstChild as HTMLElement;
    expect(el.style.width).toBe("6px");
    expect(el.className).toContain("pulse");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd projects/ui && pnpm test src/components/ui/StatusCircle src/components/ui/PriorityBars src/components/ui/PulseDot`
Expected: FAIL — modules not found.

- [ ] **Step 3: Implement the three components**

`projects/ui/src/components/ui/StatusCircle.tsx` — implement all five variants per the README's exact SVG snippets. Skeleton:
```tsx
export type WorkItemStatus = "backlog" | "todo" | "in_progress" | "in_review" | "done";

export function StatusCircle({ status, size = 13 }: { status: WorkItemStatus; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 13 13" fill="none">
      {status === "backlog" && (
        <circle cx="6.5" cy="6.5" r="4.5" stroke="#25272e" strokeWidth="1.5" strokeDasharray="2.5 2" fill="none" />
      )}
      {status === "todo" && (
        <circle cx="6.5" cy="6.5" r="4.5" stroke="#3a3d46" strokeWidth="1.5" fill="none" />
      )}
      {status === "in_progress" && (
        <>
          <circle cx="6.5" cy="6.5" r="4.5" stroke="#22252c" strokeWidth="1.5" fill="none" />
          <circle cx="6.5" cy="6.5" r="4.5" stroke="#7c6cf0" strokeWidth="1.5"
            strokeDasharray="14.14 14.14" transform="rotate(-90 6.5 6.5)" fill="none" />
        </>
      )}
      {status === "in_review" && (
        <>
          <circle cx="6.5" cy="6.5" r="4.5" stroke="#22252c" strokeWidth="1.5" fill="none" />
          <circle cx="6.5" cy="6.5" r="4.5" stroke="#52555e" strokeWidth="1.5"
            strokeDasharray="21.2 7.07" transform="rotate(-90 6.5 6.5)" fill="none" />
        </>
      )}
      {status === "done" && (
        <>
          <circle cx="6.5" cy="6.5" r="4.5" fill="#1e2028" />
          <path d="M4.5 6.5l1.5 1.5 2.5-2.5" stroke="#0b0c0f" strokeWidth="1.4"
            strokeLinecap="round" strokeLinejoin="round" />
        </>
      )}
    </svg>
  );
}
```

`projects/ui/src/components/ui/PriorityBars.tsx`:
```tsx
const LEVEL: Record<string, number> = { low: 1, medium: 2, high: 3, urgent: 3 };
const HEIGHTS = [4, 7, 10];

export function PriorityBars({ priority }: { priority: "low" | "medium" | "high" | "urgent" }) {
  const level = LEVEL[priority] ?? 0;
  return (
    <div className="flex items-end gap-[2px]">
      {HEIGHTS.map((h, i) => {
        const filled = i < level;
        return (
          <span key={i} data-bar data-filled={filled}
            style={{ width: 3, height: h, borderRadius: 1, background: filled ? "#4a4d56" : "#25272e" }} />
        );
      })}
    </div>
  );
}
```

`projects/ui/src/components/ui/PulseDot.tsx`:
```tsx
export function PulseDot({ size = 6, className = "" }: { size?: number; className?: string }) {
  return (
    <span
      className={`rounded-full bg-accent animate-[pulse_2s_infinite] ${className}`}
      style={{ width: size, height: size, boxShadow: "0 0 0 2.5px rgba(124,108,240,0.20)" }}
    />
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd projects/ui && pnpm test src/components/ui/StatusCircle src/components/ui/PriorityBars src/components/ui/PulseDot`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/components/ui/StatusCircle.tsx projects/ui/src/components/ui/PriorityBars.tsx projects/ui/src/components/ui/PulseDot.tsx projects/ui/src/components/ui/StatusCircle.test.tsx projects/ui/src/components/ui/PriorityBars.test.tsx projects/ui/src/components/ui/PulseDot.test.tsx
git commit -m "feat(ui): status circle, priority bars, pulse dot"
```

---

### Task 4: Identity & labels — Avatar, Tag, StatusBadge

**Files:**
- Create: `projects/ui/src/components/ui/Avatar.tsx`, `Tag.tsx`, `StatusBadge.tsx`
- Test: `projects/ui/src/components/ui/Avatar.test.tsx`, `Tag.test.tsx`, `StatusBadge.test.tsx`

**Interfaces:**
- Produces:
  - `Avatar({ initials, variant = "user", size = 24 }: { initials: string; variant?: "user" | "agent"; size?: number })` — `user` = circle `bg-[#1c1e26]` bordered; `agent` = rounded-square `bg-accent`; mono initials. Values per `docs/design/README.md` § Sidebar (avatar) and § Chat Panel (agent avatar).
  - `Tag({ children, tone = "default" }: { children: ReactNode; tone?: "default" | "accent" })` — the epic tag chip: `default` bordered grey mono; `accent` violet-tinted. Per § "List rows" (Epic tag) and § "Work Item Detail" (Epic tag).
  - `BadgeKind = "action_needed" | "review_needed" | "info" | "resolved" | "running" | "idle"`; `StatusBadge({ kind }: { kind: BadgeKind })` — the inbox/agent badges with the exact bg/border/text colours + label text per § Inbox "Badge types" and § Board "Agent Chip" (RUNNING/IDLE). Mono, 8.5px, 600, letter-spacing 0.03em, radius 3px.

- [ ] **Step 1: Write the failing tests**

`projects/ui/src/components/ui/Avatar.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Avatar } from "./Avatar";

describe("Avatar", () => {
  it("shows the initials", () => {
    render(<Avatar initials="JW" />);
    expect(screen.getByText("JW")).toBeInTheDocument();
  });
  it("uses a rounded square for the agent variant and a circle for user", () => {
    const { container: agent } = render(<Avatar initials="BU" variant="agent" />);
    const { container: user } = render(<Avatar initials="JW" variant="user" />);
    expect((agent.firstChild as HTMLElement).className).not.toContain("rounded-full");
    expect((user.firstChild as HTMLElement).className).toContain("rounded-full");
  });
});
```

`projects/ui/src/components/ui/Tag.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Tag } from "./Tag";

describe("Tag", () => {
  it("renders its content", () => {
    render(<Tag>AUTH</Tag>);
    expect(screen.getByText("AUTH")).toBeInTheDocument();
  });
  it("applies accent styling for the accent tone", () => {
    const { container } = render(<Tag tone="accent">AUTH</Tag>);
    expect((container.firstChild as HTMLElement).className).toContain("accent");
  });
});
```

`projects/ui/src/components/ui/StatusBadge.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("renders the right label per kind", () => {
    render(<StatusBadge kind="action_needed" />);
    expect(screen.getByText(/ACTION NEEDED/i)).toBeInTheDocument();
  });
  it("renders RUNNING for the running kind", () => {
    render(<StatusBadge kind="running" />);
    expect(screen.getByText(/RUNNING/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd projects/ui && pnpm test src/components/ui/Avatar src/components/ui/Tag src/components/ui/StatusBadge`
Expected: FAIL — modules not found.

- [ ] **Step 3: Implement the components**

`projects/ui/src/components/ui/Avatar.tsx`:
```tsx
export function Avatar({
  initials, variant = "user", size = 24,
}: { initials: string; variant?: "user" | "agent"; size?: number }) {
  const base = "inline-flex items-center justify-center font-mono font-bold text-white";
  const shape =
    variant === "agent"
      ? "rounded-[5px] bg-accent"
      : "rounded-full bg-[#1c1e26] border-[1.5px] border-[rgba(255,255,255,0.13)] text-text-3";
  return (
    <span className={`${base} ${shape}`} style={{ width: size, height: size, fontSize: size * 0.4 }}>
      {initials}
    </span>
  );
}
```

`projects/ui/src/components/ui/Tag.tsx`:
```tsx
import type { ReactNode } from "react";

export function Tag({ children, tone = "default" }: { children: ReactNode; tone?: "default" | "accent" }) {
  const styles =
    tone === "accent"
      ? "bg-accent-bg border-accent-border text-accent-text"
      : "border-border text-text-4";
  return (
    <span className={`inline-flex items-center rounded-[4px] border px-[7px] py-[2px] font-mono text-[9.5px] ${styles}`}>
      {children}
    </span>
  );
}
```

`projects/ui/src/components/ui/StatusBadge.tsx` — encode the exact colours + labels per the README badge table:
```tsx
export type BadgeKind = "action_needed" | "review_needed" | "info" | "resolved" | "running" | "idle";

const BADGES: Record<BadgeKind, { label: string; bg: string; border: string; color: string }> = {
  action_needed: { label: "ACTION NEEDED", bg: "rgba(190,65,50,0.12)", border: "rgba(190,65,50,0.20)", color: "#b05848" },
  review_needed: { label: "REVIEW NEEDED", bg: "rgba(170,130,30,0.10)", border: "rgba(170,130,30,0.18)", color: "#907030" },
  info:          { label: "INFO",          bg: "rgba(50,80,160,0.10)",  border: "rgba(50,80,160,0.18)",  color: "#4868a0" },
  resolved:      { label: "RESOLVED",      bg: "rgba(50,110,60,0.08)",  border: "rgba(50,110,60,0.14)",  color: "#3d6a48" },
  running:       { label: "RUNNING",       bg: "rgba(124,108,240,0.12)", border: "rgba(124,108,240,0.25)", color: "#bab7f6" },
  idle:          { label: "IDLE",          bg: "transparent",            border: "rgba(255,255,255,0.05)", color: "#22252c" },
};

export function StatusBadge({ kind }: { kind: BadgeKind }) {
  const b = BADGES[kind];
  return (
    <span
      className="inline-flex items-center rounded-[3px] border font-mono font-semibold tracking-[0.03em] text-[8.5px] px-[5px] py-[2px]"
      style={{ background: b.bg, borderColor: b.border, color: b.color }}
    >
      {b.label}
    </span>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd projects/ui && pnpm test src/components/ui/Avatar src/components/ui/Tag src/components/ui/StatusBadge`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/components/ui/Avatar.tsx projects/ui/src/components/ui/Tag.tsx projects/ui/src/components/ui/StatusBadge.tsx projects/ui/src/components/ui/Avatar.test.tsx projects/ui/src/components/ui/Tag.test.tsx projects/ui/src/components/ui/StatusBadge.test.tsx
git commit -m "feat(ui): avatar, tag, status badge"
```

---

### Task 5: Interactive — Button, Chip, Toggle

**Files:**
- Create: `projects/ui/src/components/ui/Button.tsx`, `Chip.tsx`, `Toggle.tsx`
- Test: `projects/ui/src/components/ui/Button.test.tsx`, `Chip.test.tsx`, `Toggle.test.tsx`

**Interfaces:**
- Produces:
  - `Button({ variant = "primary", children, ...rest })` — `variant: "primary" | "secondary" | "tertiary"`; primary = `bg-accent` white (the topbar "New" + inbox primary action), secondary = bordered `text-text-3`, tertiary = fainter bordered. Forwards native `<button>` props (incl. `onClick`, `disabled`). Sizes/padding per § Topbar "New button" and § Inbox "Quick action buttons".
  - `Chip({ children, active = false, onClick })` — the filter chip / view-switcher chip: bordered, 26px tall, 11px; `active` = `bg-[rgba(255,255,255,0.07)] text-text-2`. Per § Topbar "Filter chip" / "View switcher".
  - `Toggle({ checked, onChange }: { checked: boolean; onChange: (next: boolean) => void })` — the 26×14 switch with a 10×10 knob; on = knob right + `bg-accent`, off = knob left + `bg-[#3a3d44]`. Per § Settings "Toggle switch". Keyboard/Click accessible (role="switch", aria-checked).

- [ ] **Step 1: Write the failing tests**

`projects/ui/src/components/ui/Button.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Button } from "./Button";

describe("Button", () => {
  it("renders children and fires onClick", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>New</Button>);
    await userEvent.click(screen.getByText("New"));
    expect(onClick).toHaveBeenCalledOnce();
  });
  it("primary variant uses the accent background", () => {
    const { container } = render(<Button variant="primary">Go</Button>);
    expect((container.firstChild as HTMLElement).className).toContain("bg-accent");
  });
});
```
(Add `@testing-library/user-event` to devDependencies in Task 1's package.json if not present — version `^14.5.0`.)

`projects/ui/src/components/ui/Chip.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Chip } from "./Chip";

describe("Chip", () => {
  it("renders content and marks active state", () => {
    const { rerender, container } = render(<Chip>List</Chip>);
    expect(screen.getByText("List")).toBeInTheDocument();
    rerender(<Chip active>List</Chip>);
    expect((container.firstChild as HTMLElement).getAttribute("data-active")).toBe("true");
  });
});
```

`projects/ui/src/components/ui/Toggle.test.tsx`:
```tsx
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Toggle } from "./Toggle";

describe("Toggle", () => {
  it("exposes switch semantics and toggles on click", async () => {
    const onChange = vi.fn();
    const { getByRole } = render(<Toggle checked={false} onChange={onChange} />);
    const sw = getByRole("switch");
    expect(sw.getAttribute("aria-checked")).toBe("false");
    await userEvent.click(sw);
    expect(onChange).toHaveBeenCalledWith(true);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd projects/ui && pnpm test src/components/ui/Button src/components/ui/Chip src/components/ui/Toggle`
Expected: FAIL — modules not found (and `user-event` import resolves after adding the dep + `pnpm install`).

- [ ] **Step 3: Implement the components**

`projects/ui/src/components/ui/Button.tsx`:
```tsx
import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "tertiary";
const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-white",
  secondary: "border border-[rgba(255,255,255,0.12)] text-text-3",
  tertiary: "border border-border text-text-4",
};

export function Button(
  { variant = "primary", className = "", ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant },
) {
  return (
    <button
      className={`inline-flex items-center gap-1 rounded-[5px] px-3 h-7 text-[11.5px] font-medium disabled:opacity-50 ${VARIANTS[variant]} ${className}`}
      {...rest}
    />
  );
}
```

`projects/ui/src/components/ui/Chip.tsx`:
```tsx
import type { ReactNode } from "react";

export function Chip(
  { children, active = false, onClick }: { children: ReactNode; active?: boolean; onClick?: () => void },
) {
  return (
    <button
      data-active={active}
      onClick={onClick}
      className={`inline-flex items-center gap-1 h-[26px] px-[9px] rounded-[5px] border border-border-strong text-[11px] ${
        active ? "bg-[rgba(255,255,255,0.07)] text-text-2" : "text-text-4"
      }`}
    >
      {children}
    </button>
  );
}
```

`projects/ui/src/components/ui/Toggle.tsx`:
```tsx
export function Toggle({ checked, onChange }: { checked: boolean; onChange: (next: boolean) => void }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="relative inline-block rounded-[10px] transition-colors"
      style={{ width: 26, height: 14, background: checked ? "var(--accent)" : "#181a22" }}
    >
      <span
        className="absolute top-[2px] rounded-full transition-all"
        style={{ width: 10, height: 10, left: checked ? 14 : 2, background: checked ? "#fff" : "#3a3d44" }}
      />
    </button>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd projects/ui && pnpm test src/components/ui/Button src/components/ui/Chip src/components/ui/Toggle`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/components/ui/Button.tsx projects/ui/src/components/ui/Chip.tsx projects/ui/src/components/ui/Toggle.tsx projects/ui/src/components/ui/Button.test.tsx projects/ui/src/components/ui/Chip.test.tsx projects/ui/src/components/ui/Toggle.test.tsx projects/ui/package.json
git commit -m "feat(ui): button, chip, toggle"
```

---

### Task 6: Feedback & containers — ProgressBar, Card, MetricCard, TypingIndicator

**Files:**
- Create: `projects/ui/src/components/ui/ProgressBar.tsx`, `Card.tsx`, `MetricCard.tsx`, `TypingIndicator.tsx`, and `projects/ui/src/components/ui/index.ts` (barrel re-export of all primitives + icons)
- Test: `projects/ui/src/components/ui/ProgressBar.test.tsx`, `MetricCard.test.tsx`, `TypingIndicator.test.tsx`, `index.test.ts`

**Interfaces:**
- Consumes: all prior primitives + icons (for the barrel).
- Produces:
  - `ProgressBar({ value, tone = "accent", height = 3 }: { value: number; tone?: "accent" | "muted"; height?: number })` — `value` is 0..1; track `bg-[#181a20]`, fill `bg-accent` (accent) or `bg-[#44474f]` (muted), rounded 1px. Per § Detail "TOKEN USAGE" + § Board agent chip progress.
  - `Card({ children, className })` — surface container: `bg-bg-surface border border-border rounded-[8px]`. Per § Dashboard metric cards / settings cards.
  - `MetricCard({ label, value, sub, accent = false })` — dashboard metric card: mono label (`text-text-6`), 30px value, sub-text; `accent` adds the accent border. Per § Dashboard "Metric cards row".
  - `TypingIndicator()` — three 5px dots with staggered pulse (delays 0/0.25/0.5s) per § Animation / § Chat Panel.
  - `components/ui/index.ts` barrel exporting every primitive + `* from "./icons"`.

- [ ] **Step 1: Write the failing tests**

`projects/ui/src/components/ui/ProgressBar.test.tsx`:
```tsx
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProgressBar } from "./ProgressBar";

describe("ProgressBar", () => {
  it("renders a fill width proportional to value", () => {
    const { container } = render(<ProgressBar value={0.5} />);
    const fill = container.querySelector("[data-fill]") as HTMLElement;
    expect(fill.style.width).toBe("50%");
  });
  it("clamps out-of-range values", () => {
    const { container } = render(<ProgressBar value={1.5} />);
    expect((container.querySelector("[data-fill]") as HTMLElement).style.width).toBe("100%");
  });
});
```

`projects/ui/src/components/ui/MetricCard.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MetricCard } from "./MetricCard";

describe("MetricCard", () => {
  it("shows label, value and sub-text", () => {
    render(<MetricCard label="ACTIVE AGENTS" value="4" sub="3 running" />);
    expect(screen.getByText("ACTIVE AGENTS")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("3 running")).toBeInTheDocument();
  });
});
```

`projects/ui/src/components/ui/TypingIndicator.test.tsx`:
```tsx
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TypingIndicator } from "./TypingIndicator";

describe("TypingIndicator", () => {
  it("renders three animated dots", () => {
    const { container } = render(<TypingIndicator />);
    const dots = container.querySelectorAll("[data-dot]");
    expect(dots).toHaveLength(3);
    expect((dots[0] as HTMLElement).className).toContain("pulse");
  });
});
```

`projects/ui/src/components/ui/index.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import * as ui from "./index";

describe("ui barrel", () => {
  it("re-exports the core primitives and icons", () => {
    for (const name of ["Button", "Chip", "Toggle", "Avatar", "Tag", "StatusBadge",
      "StatusCircle", "PriorityBars", "PulseDot", "ProgressBar", "Card", "MetricCard",
      "TypingIndicator", "PlusIcon"]) {
      expect(ui[name as keyof typeof ui]).toBeTypeOf("function");
    }
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd projects/ui && pnpm test src/components/ui/ProgressBar src/components/ui/MetricCard src/components/ui/TypingIndicator src/components/ui/index`
Expected: FAIL — modules not found.

- [ ] **Step 3: Implement the components + barrel**

`projects/ui/src/components/ui/ProgressBar.tsx`:
```tsx
export function ProgressBar(
  { value, tone = "accent", height = 3 }: { value: number; tone?: "accent" | "muted"; height?: number },
) {
  const pct = `${Math.max(0, Math.min(1, value)) * 100}%`;
  return (
    <div className="w-full rounded-[1px] bg-[#181a20]" style={{ height }}>
      <div data-fill className={`h-full rounded-[1px] ${tone === "accent" ? "bg-accent" : "bg-[#44474f]"}`} style={{ width: pct }} />
    </div>
  );
}
```

`projects/ui/src/components/ui/Card.tsx`:
```tsx
import type { ReactNode } from "react";
export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`bg-bg-surface border border-border rounded-[8px] ${className}`}>{children}</div>;
}
```

`projects/ui/src/components/ui/MetricCard.tsx`:
```tsx
import type { ReactNode } from "react";
import { Card } from "./Card";

export function MetricCard(
  { label, value, sub, accent = false }: { label: string; value: ReactNode; sub?: ReactNode; accent?: boolean },
) {
  return (
    <Card className={`p-[15px] ${accent ? "border-accent-border" : ""}`}>
      <div className="font-mono text-[9.5px] tracking-[0.07em] text-text-6">{label}</div>
      <div className="mt-2 text-[30px] font-semibold text-text-1 leading-none">{value}</div>
      {sub && <div className="mt-1 text-[11px] text-text-5">{sub}</div>}
    </Card>
  );
}
```

`projects/ui/src/components/ui/TypingIndicator.tsx`:
```tsx
export function TypingIndicator() {
  const delays = ["0s", "0.25s", "0.5s"];
  return (
    <div className="flex items-center gap-1">
      {delays.map((d, i) => (
        <span key={i} data-dot className="rounded-full bg-[#3a3d44] animate-[pulse_1.2s_infinite]"
          style={{ width: 5, height: 5, animationDelay: d }} />
      ))}
    </div>
  );
}
```

`projects/ui/src/components/ui/index.ts`:
```ts
export * from "./icons";
export { StatusCircle } from "./StatusCircle";
export type { WorkItemStatus } from "./StatusCircle";
export { PriorityBars } from "./PriorityBars";
export { PulseDot } from "./PulseDot";
export { Avatar } from "./Avatar";
export { Tag } from "./Tag";
export { StatusBadge } from "./StatusBadge";
export type { BadgeKind } from "./StatusBadge";
export { Button } from "./Button";
export { Chip } from "./Chip";
export { Toggle } from "./Toggle";
export { ProgressBar } from "./ProgressBar";
export { Card } from "./Card";
export { MetricCard } from "./MetricCard";
export { TypingIndicator } from "./TypingIndicator";
```

- [ ] **Step 4: Run the full suite + gates**

Run: `cd projects/ui && pnpm test && pnpm lint && pnpm build`
Expected: all component tests PASS; eslint + tsc clean; build succeeds.

- [ ] **Step 5: Commit**

```bash
git add projects/ui/src/components/ui
git commit -m "feat(ui): progress bar, card, metric card, typing indicator + barrel"
```

---

## Self-Review

**1. Spec coverage (against the A2 spec §6 Design system + §5 structure + §9 gates):** Task 1 covers scaffold + tokens (§5 structure root, §6 tokens). Tasks 2–6 cover every named primitive in §6 (Icon set, StatusCircle, PriorityBars, PulseDot, Avatar, Tag, StatusBadge, Button, Chip/FilterChip→Chip, Toggle, ProgressBar, Card, MetricCard, TypingIndicator) + the barrel. `KanbanCard`/`ListRow` from §6 are deliberately deferred to the Board plan (they consume WorkItem data shapes from the data-layer plan) — noted here so it isn't read as a gap. Data layer, shell, screens, routing are explicitly out of scope (later plans). Gates (`pnpm lint`/`test`/`build`) run each task and in Task 6 Step 4.

**2. Placeholder scan:** No "TBD"/"implement later". The two places that reference external sources — icon SVG geometry (from `NAAF Hi-Fi.dc.html`) and exact token/anatomy values (from `docs/design/README.md`) — are deliberate: that data is authoritative in-repo and transcribing it wholesale into the plan would be error-prone duplication. Each such task names the exact section/file and gives the complete component pattern + a fully-worked example, so the work is mechanical.

**3. Type consistency:** `IconProps = { size?; className? }` used by every icon and the icons test. `WorkItemStatus` defined in `StatusCircle.tsx`, re-exported via the barrel. `BadgeKind` defined in `StatusBadge.tsx`, re-exported. `ProgressBar` `value` is 0..1 in both its def and test (50%/clamp). `Toggle` `onChange(next: boolean)` matches its test. `MetricCard` props (`label/value/sub/accent`) match its test. Barrel export names match `index.test.ts`. `Button` forwards native props (onClick tested). No dangling references.
