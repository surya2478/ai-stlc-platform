# UI Redesign Audit: AI STLC Command Center

This document outlines the current state of the frontend UI, layout, components, and styling, and establishes the path for upgrading it to a premium, modern **AI STLC Command Center** with a consistent design system.

---

## 1. Current UI Inspection & Structural Audit

The frontend is a **Next.js App Router** project styled with **Tailwind CSS**, utilising several headless Radix UI primitives.

### Layout Shell
* **Header (`src/components/layout/Header.tsx`)**:
  * Simple white top bar with basic search placeholder, "New Project" button, notification bell, and a basic user logout circle.
  * Lacks advanced contextual dropdowns (e.g., Project selector, Environment selector, Jira sync indicator) shown in the target design.
* **Sidebar (`src/components/layout/Sidebar.tsx`)**:
  * Currently uses standard light-themed background (`bg-card` which resolves to white in light mode) with a light gray border.
  * Nav items are grouped simply.
  * Lacks a collapse/expand mechanism, executive styling, and the deep navy sidebar aesthetics.

### Page Components & Styling
* **Dashboard (`src/app/dashboard/page.tsx`)**:
  * Simple grid of stat cards.
  * Lacks a cohesive "Executive Release Readiness" section.
  * Lacks the interactive, visual **STLC Pipeline Tracker** showing end-to-end completion rates.
  * Charts are minimal: custom SVG-based bar-like charts for execution trends instead of high-fidelity Recharts visualisations.
  * Recent activity and agent status are styled as basic vertical lists with generic borders.
* **Tables and Detail Forms (e.g., `src/app/test-cases/page.tsx`)**:
  * Uses a grid layout styled with custom tailwind widths to simulate columns.
  * Row expansion occurs vertically inline, pushing content down and creating clutter.
  * Columns selector and saved views are present but styled with native form selectors and non-standard popovers.
  * Lacks a modern right-side detail drawer pattern.

---

## 2. Reusable Components & Design Tokens Identified

We will define standard tokens in `src/app/globals.css` and create atomic, highly styled components in `src/components/ui` to achieve Carbon/Fluent/Fiori level premium design.

### A. Design Tokens (CSS Variables in `src/app/globals.css`)
* **Sidebar Dark Navy Theme**: Custom variables for navy backgrounds (`#0B132B`, `#0F172A`) and subtle active backgrounds.
* **Blue Primary Colors**: Standardizing on professional enterprise blue (`#1B59F8` or `#2563EB`) with interactive states.
* **AI Accents**: Linear gradient and glow tokens for cyan/violet AI accents (`#06B6D4` / `#8B5CF6`).
* **Grids & Spacing**: Strict 8px spacing standard (`space-y-2` -> 16px, `p-6` -> 24px, `gap-4` -> 32px, etc.).

### B. Standardized Components to Create (`src/components/ui/`)
1. **`Button`**: Consistent enterprise buttons with custom variants (primary, secondary, ghost, AI accent).
2. **`Card`**: White card wrapper with light shadow, optional AI neon-accent header border, and standardized padding.
3. **`Badge` (Status Chips)**: Standardized colored pills with clean background-border-text combos for statuses (e.g., Passed, Failed, Synced, In Progress, Pending).
4. **`Drawer`**: Right-side sliding panel for details (replacing the vertical inline expander).
5. **`Select` / `Input`**: Clean, border-tinted custom input elements matching IBM Carbon style.
6. **`Table`**: Modern compact table component with proper spacing, hover states, and column controls.

---

## 3. Proposed Files to Modify

To implement the upgrade without breaking existing backend integrations, we will target the following files:

### Shell & Global Styles
* `src/app/globals.css` — Extend variables for light mode, deep navy sidebar, and AI gradients.
* `src/components/layout/Sidebar.tsx` — Implement the deep navy sidebar, header logo, and collapse toggle.
* `src/components/layout/Header.tsx` — Add project selector dropdown, environment dropdown, Jira sync status, and user avatar.

### Atomic Design System (`src/components/ui/`)
* `src/components/ui/card.tsx` [NEW]
* `src/components/ui/button.tsx` [NEW]
* `src/components/ui/badge.tsx` [NEW]
* `src/components/ui/drawer.tsx` [NEW]
* `src/components/ui/table.tsx` [NEW]

### Page Redesigns
* `src/app/dashboard/page.tsx` — Complete overhaul to Command Center layout (Release Readiness, Pipeline tracker, Recharts, Jira sync status, AI activity list, Pending approvals list).
* `src/app/test-cases/page.tsx` — Revamp table, integrate Right Detail Drawer, clean up Presets/Columns selector.
* `src/app/test-data/page.tsx` — Standardize layout with compact table + right drawer.
* `src/app/automation/page.tsx` — Standardize automation candidate table.
* `src/app/execution/page.tsx` — Standardize execution run logs.
* `src/app/defects/page.tsx` — Overhaul defect tracking list.
* `src/app/reports/page.tsx` — Refine report visualisations.

---

## 4. Verification & Validation Plan
* **Lint Check**: Run `npm run lint` in the `frontend` folder to guarantee TypeScript and ESLint compliance.
* **Build Check**: Run `npm run build` in the `frontend` folder to ensure successful Next.js output.
* **Backend Cohesion**: Maintain all current state selectors, callbacks, and API calls to keep all data inputs live and fully integrated.
