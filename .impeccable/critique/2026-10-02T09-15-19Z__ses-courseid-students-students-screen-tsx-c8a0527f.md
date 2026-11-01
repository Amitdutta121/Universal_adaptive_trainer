---
target: Classrooms screen
total_score: 20
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 3
target_identity: "file:C:\\Users\\amit\\orca\\workspaces\\FInalAdaptiveTrainer\\main-2\\frontend\\src\\app\\courses\\[courseId]\\students\\students-screen.tsx"
target_fingerprint: "sha256:9ee950d04dbfd35cbd7832a52f7f6f199aa91f00b977d7ff3dc34af8002d2a12"
target_path: "C:\\Users\\amit\\orca\\workspaces\\FInalAdaptiveTrainer\\main-2\\frontend\\src\\app\\courses\\[courseId]\\students\\students-screen.tsx"
timestamp: 2026-10-02T09-15-19Z
slug: ses-courseid-students-students-screen-tsx-c8a0527f
---
# Critique: Classrooms (/courses/[courseId]/students) — 20/40
Method: dual-agent (A: design review · B: detector + browser)

Heuristics: 1=3 visibility (toast-only success) · 2=1 jargon (frozen set/snapshot/taxonomy/lobby/v7) · 3=2 unguarded Update, no revert · 4=2 two copy labels, inconsistent row click · 5=2 no update diff · 6=2 header taxonomy switch changes app-wide taxonomy · 7=2 no keyboard row select/bulk · 8=1 3 snapshot views, 13 actions in first viewport · 9=3 QueryError real messages · 10=2 inline help in jargon.

Specificity: model specific (stable per-taxonomy link, pinned snapshots); presentation generic shadcn (eyebrow+CardTitle x2, 3 stat tiles, 3 tables).
Detector: CLI clean (0). Overlay 23: real on-screen = 9.9px "Taxonomy" label, 9.6px "v7" badge, 4.3:1 muted labels, nested bg-muted/30 tiles + Card-in-Card, header pill border+28px shadow. False positives: text-occlusion (Claude extension badge), 2x illustration (dev tooling). Shell-level: 5 layout-transition (sidebar), brand-mark gradient, 10.9px Theme.

Priority issues:
- [P1] Two link types + three snapshot views (L195 vs L387; select L486 + table L502). Fix: one classroom link above fold; collapse "One snapshot" into Snapshot history (one table). distill -> layout.
- [P1] "Update" re-points live link with no confirm/diff/revert (L237, L308). Fix: confirm with diff + Revert to #N. harden.
- [P1] Empty state for no-taxonomy course says "Create the classroom link above" but card is hidden (L190 vs L338-343). Fix: branch on taxonomyId === null, link to Curriculum. onboard.
- [P2] Jargon copy (L179, L351, L363, L372 "94 / 94"). clarify.
- [P2] View contents: one GET per question (L123-136), table overflow, raw markdown in truncate (L56). optimize -> polish.

Personas: Alex — click-only <tr onClick> L512, no bulk update, taxonomy switch side effect. Sam — 3x Copy/3x Update/2x Create link without row context; title overrides disabled name; no live regions for Copied/Freezing; color-only selected row; 4.3:1 contrast. Jordan — jargon before instruction; "Open lobby" resumes instructor's own student session; Classrooms not nameable.

Minor: select trigger overflows card; lobby leaks "Instructor Studio" title/footer; formatDate(null)->"Open" L43; empty link on first paint + CopyButton not disabled; mobile (source only) 5-col table no overflow wrapper.

Questions: who needs a pinned per-snapshot link? should live-changing Update ever be one click / move to publish flow? is this a "Share & versions" tab on Roster?
