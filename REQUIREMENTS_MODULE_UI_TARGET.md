# TARGET REQUIREMENTS MODULE DESIGN SPECIFICATION

**Document Name:** REQUIREMENTS_MODULE_UI_TARGET.md  
**Product:** e& AI Test Automation System  
**Interface:** Requirements Command Center  
**Theme:** Enterprise Light (Slate/White) with Deep Navy Navigation Sidebar, Cyan/Violet AI Accents, and Rich Semantic Badges.

---

## Visual Mockup & Interactive Prototype

### Mockup Image
The proposed user interface layout:

<img src="/C:/Users/banot/.gemini/antigravity/brain/23619750-d21f-4a01-b8e7-a11a0a9fc3fe/requirements_command_center_mockup_1781246028135.png" alt="Requirements Command Center Mockup" style="max-width: 100%; border: 1px solid #e2e8f0; border-radius: 12px; margin-top: 12px;">

### High-Fidelity Mockup Code
* **Interactive Prototype Source:** [requirements-command-center.html](file:///C:/Users/banot/.gemini/antigravity/brain/23619750-d21f-4a01-b8e7-a11a0a9fc3fe/requirements-command-center.html)
* **Workspace Reference Copy:** [requirements-command-center.html](file:///c:/Test_AI_Agents/Test_AI_Agents/stlc-platform/frontend/design-mockups/requirements-command-center.html)

---

## 1. Visual Theme & Design Tokens

To align with the **AI STLC Command Center** design language, the Requirements Command Center uses a clean, premium dashboard layout. 

### Color Palette
* **Sidebar:** Deep Navy (`#0b1329`) with Slate Blue icons.
* **Workspace Background:** Warm Light Gray (`#f8fafc`).
* **Primary Actions:** Enterprise Blue (`#1b59f8`).
* **AI Accents/Gradients:** Violet/Indigo gradient (`linear-gradient(135deg, #7c3aed, #4f46e5)`) to emphasize AI quality checks.
* **Status Badges:**
  * **Approved / Synced / Connected:** Emerald Green (`bg-emerald-50 text-emerald-700 border-emerald-250`)
  * **Draft / Offline:** Slate Gray (`bg-slate-100 text-slate-600 border-slate-200`)
  * **Needs Review / Pending:** Amber/Orange (`bg-amber-50 text-amber-700 border-amber-250`)
  * **Rejected / Failed / Conflict:** Crimson Red (`bg-rose-50 text-rose-700 border-rose-250`)

### Typography
* **Primary Font:** `Inter` or `Outfit` from Google Fonts.
* **Fallback:** System Sans-Serif.

---

## 2. Layout Structure

The layout is split into a fixed left-hand navigation sidebar, a main workspace container, and a right-side sliding drawer that appears when selecting any requirement row.

```text
+------------------------------------------------------------------------------------+
| SIDEBAR   | HEADER: Requirements Command Center (Filters: Project, Release, Env)   |
| (Navy)    | Buttons: [Sync Jira] [Upload Doc] [Add Req] [Evaluate Quality]         |
|           +------------------------------------------------------------------------+
|           | SUMMARY CARDS (Total, Approved, Needs Clarification, Jira Synced, etc.)|
|           +------------------------------------------------------------------------+
|           | READINESS PIPELINE (Draft -> AI Reviewed -> Approved -> Test Plan Gen) |
|           +------------------------------------------------------------------------+
|           | SMART FILTERS (All, Draft, High Risk, Billing, CRM, OSS/BSS)           |
|           +------------------------------------------------------------------------+
|           | MAIN REQUIREMENTS TABLE                                                |
|           | ID      | Jira Key | Title           | Domain  | Quality | Status | ...|
|           | REQ-001 | STLC-12  | Update Billing  | Billing | 4.8/5   | Approved    |
|           | REQ-002 | STLC-15  | Mobile Checkout | Mobile  | 2.1/5   | Pending     |
+-----------+------------------------------------------------------------------------+
```

---

## 3. Component Details

### A. Header (Global Bar)
* **Title:** `Requirements Command Center` (Font size: `1.5rem`, Font weight: `Bold`, Color: `#0f172a`).
* **Subtitle:** `AI-powered requirement intelligence, Jira sync, quality review, approval governance, and test planning readiness.` (Font size: `0.875rem`, Color: `#64748b`).
* **Top Controls Layout:**
  * **Project Selector:** Dropdown showing current e& project name.
  * **Release Selector:** Dropdown (e.g., `Release 2026.Q2`, `Hotfix 5.1`).
  * **Environment Selector:** Dropdown (e.g., `SIT-Core`, `UAT-Billing`).
  * **Jira Sync Health:** A small indicator dot with a pulse effect (Green = Connected, Red = API Error).
  * **Action Buttons:**
    * **Jira Sync Button:** Call `POST /api/v1/jira/connections/{id}/import-requirements` (`#1b59f8`).
    * **Upload Document Button:** Icon-only file upload zone or button.
    * **Add Requirement:** Manual inline popup model creation.
    * **Evaluate Quality:** Violet background button to run Agent 2 on selected or all requirements.

### B. Summary Cards
Four high-fidelity cards arranged in a single row:
1. **Total Requirements:** Big text with count, subtext showing percentage split of sources (e.g., *"65% Jira, 35% Docs"*).
2. **Approved Spec:** Big green count, subtext showing percentage of total requirements (e.g., *"84.5% ready for testing"*).
3. **Needs Clarification:** Big amber count. Shows requirements marked as `needs_clarification` by the AI quality agent or human reviewers.
4. **Jira Sync Conflicts:** Big red count. Triggers when a local requirement's content differs from the synced Jira ticket.

### C. Requirement Readiness Pipeline (Visual Progress Tracker)
A horizontal chain of chevron-shaped stages showing count and percentage of requirements at each lifecycle phase:
```text
[ 15.0% Draft ] -> [ 32.5% AI Reviewed ] -> [ 7.5% Clarifications ] -> [ 45.0% Approved ] -> [ 30.0% Test Plan Gen ]
```
Clicking any phase filters the main table below to show only items in that phase.

### D. Smart Filters (Quick Tabs)
A horizontal pill bar:
* `All` | `Draft` | `AI Review Pending` | `Needs Clarification` | `Approved` | `High Risk` | `Missing Acceptance Criteria` | `Jira Conflict` | `OSS/BSS` | `Mobile` | `Billing`

---

## 4. Main Requirements Table

A compact data table designed for high information density.

### Default Columns
1. **ID:** Monospace font `#1b59f8`, e.g., `REQ-001`. Clicking opens the drawer.
2. **Jira Key:** Monospace tag linked to external Jira URL, e.g., `STLC-123`.
3. **Title:** Bold text, maximum 300px width (with CSS `truncate` ellipsis).
4. **Telecom Domain:** Badged. Value: `Mobile` (blue), `Billing` (violet), `CRM` (amber), `OSS/BSS` (purple).
5. **Downstream Risk:** Badge. Value: `High` (red), `Medium` (orange), `Low` (gray).
6. **AI Quality Score:** Visual rating bar (e.g., filled stars or numeric `4.2/5`) with color coding (Green >= 4.0, Amber 3.0-3.9, Red < 3.0).
7. **Readiness Status:** Badge. Value: `Draft`, `Needs Review`, `Approved`, `Clarification Needed`.
8. **Jira Sync Status:** Icon indicating `Synced` (checkmark), `Pending Sync` (clock), or `Conflict` (alert triangle).
9. **Traceability Coverage:** Compact icons displaying what downstream artifacts exist:
   * `TP` (Test Plan): Filled icon if generated.
   * `TS` (Scenarios): Small count badge, e.g., `3`.
   * `TC` (Test Cases): Small count badge, e.g., `12`.
10. **Actions:** Row-level operations (`Edit`, `Delete`, `Trigger AI Review`).

---

## 5. Right-Side Detail Drawer

When a user clicks on a requirement ID or the "Details" button, a right-side drawer slides in from the right edge, covering 40% of the screen.

### Drawer Tabs
The drawer is organized into tabs to prevent vertical clutter:

1. **Overview Tab:**
   * Shows Title, Description, Telecom Domain selector, Impacted Systems tags, and Impacted Interfaces.
2. **Acceptance Criteria Tab:**
   * Lists the extracted bulleted criteria. Includes checkmarks allowing QA to manually sign off on individual criteria.
3. **AI Quality Review Tab:**
   * Displays the detailed scores from the Quality Agent:
     * Clarity Score (`1-5`)
     * Completeness Score (`1-5`)
     * Testability Score (`1-5`)
     * Ambiguities list, contradictions list, missing environment details, and suggested negative test cases.
4. **Jira Sync Tab:**
   * Shows Jira connection status, last sync timestamp, and a split-pane comparison if there is a conflict between local changes and Jira updates.
5. **Approval History Tab:**
   * Timeline view displaying who approved or rejected the requirement, with timestamps and review notes.
6. **Linked Artifacts Tab:**
   * Displays the traceability tree: links to the generated `Test Plan`, lists of `Test Scenarios`, `Test Cases`, and `Automation Scripts`.

---

## 6. Requirement Improvement Assistant Panel

Inside the **AI Quality Review** tab, a prominent button appears: **"Improve Requirement"**. 

When clicked, the drawer splits or shows a side-by-side modal:
* **Left Column:** Original raw requirement text.
* **Right Column:** Proposed improved text generated by the AI (incorporating missing acceptance criteria, fixing ambiguous phrasing, adding positive/negative boundary conditions, and documenting NFRs).
* **Footer Controls:**
  * **[Review Changes]** — Highlights additions in green and deletions in red.
  * **[Approve & Apply]** — Replaces the local draft with the improved text and transitions status to `ready_for_test_planning`.
  * **[Cancel]** — Discards the suggestions.
