# Provikom MVP Blockers

## Open Blockers

### B-001: Project 2024 original Java sources unavailable

- Impact: Phase 3 cannot test the original seven games through SwingJS.
- Evidence: No `.java` source files were found under the project-2024
  workspace at the start of MVP work.
- Policy: Do not fabricate source availability or substitute decompiled JARs.
- Mitigation: Use the repository's Java 8 Swing fixtures and document that they
  are not the original games.

### B-002: SwingJS/Java2Script licensing and notices unresolved

- Impact: Generated SwingJS runtime sites cannot be published.
- Evidence: `docs/SWINGJS_LICENSING.md`.
- Mitigation: Keep artifacts under ignored `build/`, document obligations, and
  do not upload the full runtime site.

### B-003: CheerpJ Community Edition usage approval unknown

- Impact: Public deployment approval is not available.
- Mitigation: Keep generated CheerpJ artifacts local/PR-gated; do not deploy.

### B-004: Student JAR redistribution permission unknown

- Impact: Duplicating game JARs in the portal may not be publishable.
- Mitigation: Repository owner must obtain permission; release gate stays closed.

### B-005: Legacy gameplay not visually accepted

- Impact: Snake's initial canvas can appear blank until the first center click;
  after input it repaints, but gameplay is still unverified. Froggie,
  Minesweeper, and Pong also need manual acceptance.
- Evidence: `project-2024/docs/MILESTONE_5_VALIDATION.md` and
  `project-2024/docs/verification/3a-integration.json` (54/54 local checks).
- Mitigation: Record launcher/repaint/teardown evidence separately; do not claim
  gameplay verification.

## Closed Blockers

None.
