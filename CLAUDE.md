# Claude Code Repository Instructions

Read the full handover before changing this repository:

- `docs/autonomous-automation-lab/CLAUDE_CODE_HANDOVER.md`
- `docs/autonomous-automation-lab/nxtqa-aaf-implementation-tracker.md`
- The approved UI contract and reference image for the screen being implemented.

## Non-negotiable delivery rules

1. The locked product scope is 58 functional screens (`UI-001` through `UI-058`).
2. Follow the phase/section order in the tracker. The next ordered screen is `UI-014 Application Registry`.
3. Do not implement a screen until its reference image and UI contract are approved by the user.
4. Match the existing page shell, compact spacing, typography, navigation and colour system used by the live application.
5. Extend existing routes/workspaces instead of creating duplicate top-level pages.
6. Do not mock values, fabricate API responses, guess business rules or show static demo counts as live data.
7. Every visible action must call a real authorized backend operation, navigate to a real route, or be clearly disabled with an explanation.
8. Agents perform analysis, generation, validation, mapping and evidence work. Humans intervene for unresolved business clarification, exceptions and independent approval gates. Routine stage advancement should be automatic after deterministic gates pass.
9. Preserve provenance, RBAC, audit history, deterministic status ownership and stage eligibility.
10. Never print, copy or commit credentials from `.env`. It may be read locally for browser login only.
11. Preserve unrelated user changes and untracked files. Never reset or discard a dirty worktree.
12. Validate frontend lint/typecheck/build, focused backend tests and the live browser flow before declaring a screen complete.

## Current repository state

- Repository: `D:\AI\Projects\stlc-platform`
- Branch: `security/hardening-v1`
- Current implemented/partially implemented AAF range: `UI-001`, `UI-006` through `UI-013`.
- Current uncommitted work contains the Requirement Analysis clarification-resolution fix. Review and preserve it before further implementation.
- `UI-001` is at `/autonomous-lab/missions`; `/dashboard` must remain the original dashboard.
- Requirements reuse `/requirements?project=<id>&view=intake|analysis|traceability|review`.
- Test Design reuses `/test-cases?project=<id>&view=generated|editor|journey-graph|approval`.

Do not treat a visually present screen as complete until the detailed handover's limitations and acceptance checklist are resolved.

