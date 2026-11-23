# Provikom MVP Progress

Last updated: 2026-11-23
Active branch: `milestone-2c1-swingjs-source-adapter`
Base converter commit: `de4a505`
Converter PR: #5 (this branch)
Project 2024 PR: #1, head `6a17f89`
Project 2024 publishing PR: #2, stacked on #1

## Status Summary

| Milestone | Status | Evidence / next action |
|---|---|---|
| 0 Planning and tracking | VERIFIED | Plan, progress, decisions and blockers committed; refresh at each milestone. |
| 1 Project 2024 Milestone 3A | VERIFIED | PR #1 CI run `44885053659` passed; awaiting human merge approval. |
| 2 SwingJS source adapter 2C.1 | VERIFIED | Two fixtures built/verified in Chromium; hosted PR CI passed on previous head f74cfa0 (runs 45107000316/45107000328); fresh hardening CI still required. |
| 3 Real-project compatibility | VERIFIED | Two independent fixtures (`swing-poc`, `swing-widgets`) built and verified; original project sources remain unavailable (B-001). |
| 4 Reproducible publishing | VERIFIED | Portal adapter tests 13/13; project-2024 PR #2 hosted offline CI passed (run 45106974783). Not an authorization to publish. |
| 5 Project 2024 validation 3B | IN_PROGRESS | Matrix added in project-2024 `docs/MILESTONE_5_VALIDATION.md`; generated players and Snake launcher/repaint verified; manual legacy gameplay acceptance remains blocked (B-005). |
| 6 Security and documentation | IN_PROGRESS | Source-staging whitelist, -proc:none and regression tests added; fresh CI and trust-boundary review required. |

## Completed Work

- Verified both repository locations after workspace move:
  - java-converter worktree: detached at `de4a505`; `origin/main` matches.
  - project-2024: `feature/converter-pilot-integration` at `6a17f89`;
    `origin/main` at `cf35f7d`.
- Rechecked PR #1: OPEN, MERGEABLE, both CI jobs successful.
- Created branch `milestone-2c1-swingjs-source-adapter`.
- Implemented `provikom_converter/swingjs/`:
  - `pins.py`, `toolchain.py`: pinned JDK/Eclipse/Java2Script/SwingJS hashes
    and managed/explicit toolchain resolution.
  - `source.py`: `src/**/*.java` validation, main-class selection, source hash,
    JavaFX/SWT rejection, audio/risky-API warnings, symlink rejection.
  - `builder.py`: real `javac --release 8` + headless Eclipse Java2Script build,
    root-level artifact, sanitized entry, manifest, evidence, ownership marker,
    atomic publish.
  - `verify.py`: headless Chromium canvas/JS checks plus POC state checks for
    timer, arrows, pause, and reset.
- Extended `build_safety.py` for source output validation, SwingJS ownership,
  and source/generated-JavaScript hash validation.
- Added CLI commands `build-project` and `verify-swingjs`.
- Updated the SwingJS adapter plan to remove decompilation claims and reject
  JAR input with a pointer to `build-project`.
- Added `docs/SWINGJS_SOURCE_ADAPTER.md` and README usage documentation.
- Added `tests/test_swingjs_source.py` (20 tests; integration tests run when the
  pinned toolchain is installed).
- Added `examples/swing-widgets`, a second independent Java 8 source fixture
  exercising BorderLayout, JButton, JLabel, MouseAdapter, Timer, and Graphics2D.
- Extended `verify-swingjs` with the opt-in `FIXTURE ticks=... clicks=...`
  protocol for timer and mouse-click evidence.
- Normalized Java2Script wall-clock comments and proved identical generated
  JavaScript bytes across two clean builds of the same source.
- Rebuilt and re-verified both fixtures after normalization, replacing the
  pre-normalization evidence and screenshots.
- Built and verified both fixtures:
  - `build/swingjs-adapter-poc`: canvas, graphics, generated JS, timer, arrows,
    pause, reset.
  - `build/swingjs-widgets`: canvas, graphics, generated JS, timer, mouse click.
- Added durable evidence:
  - `docs/verification/swingjs-adapter-poc.json`
  - `docs/verification/swingjs-widgets.json`
  - `docs/screenshots/swingjs-adapter-poc.png`
  - `docs/screenshots/swingjs-widgets.png`
- Added `docs/MILESTONE_3_COMPATIBILITY.md` with API coverage, limitations, and
  required source changes.
- Implemented project-2024 source-artifact publishing support:
  - `tools/adapt_generated_artifact.py` recognizes `swingjs` artifacts;
  - validates ownership, marker digest, generated-JS hash, source hash, and
    path containment;
  - rejects external SwingJS `serverURL` values and path traversal;
  - returns a no-op for valid source artifacts while preserving the CheerpJ
    `/app/` -> `/str/` bridge and idempotent marker refresh.
- Extended `tools/test_adaptation.py` from 7 to 13 tests covering SwingJS no-op,
  tampering, external URL, symlinked entry, and path safety.
- Added project-2024 `docs/MILESTONE_4_PUBLISHING.md` and
  `docs/MILESTONE_5_VALIDATION.md`.
- Investigated Snake's blank legacy canvas: the applet can remain unpainted
  until a center click; the updated pilot check verifies a non-blank repaint
  (71 -> 208 unique colors) without claiming playable gameplay.
- Refreshed the external pilot evidence to 54/54 checks and updated the Snake
  screenshot.

## Tests Already Executed

Project 2024 (on PR #1 head `6a17f89`, before MVP work):
- `python3 tools/verify_static.py`: 68/68 passed.
- `python3 tools/test_adaptation.py`: 7/7 passed.
- `python3 tools/verify_offline.py`: 20/20 passed.
- GitHub Actions run `44885053659`: both jobs passed.

Converter (MVP branch):
- Full non-browser suite:
  `PROVIKOM_GAMES_DIR=.../project-2024/games PROVIKOM_SKIP_BROWSER=1
  PROVIKOM_SWINGJS_TOOLCHAIN=... python3 -m unittest discover -s tests -v`:
  119 tests, 115 passed, 4 browser tests skipped.
- Both source fixtures rebuilt and verified in headless Chromium after
  Java2Script timestamp normalization.
- Artifact ownership validation passed after build and verification.
- `build-project` refuses source/ancestor output paths and non-Provikom output.
- Manifest schema validation passed for both source artifacts and all four demo
  manifests.
- Python wheel build includes the packaged headless builder plugin sources.
- Hardening: the Eclipse workspace stages only inspected Java sources; `javac --release 8 -proc:none` blocks annotation processor discovery in the initial Java compilation. This is **not a sandbox** for hostile Java projects.
- Hosted PR CI on the preceding commit `f74cfa0` succeeded: [CI (3/3 jobs)](https://github.com/AsistenProvikom/java-converter/actions/runs/45107000316) and [SwingJS reproduction (1/1 job)](https://github.com/AsistenProvikom/java-converter/actions/runs/45107000328). Fresh head checks must be verified after hardening.

Project 2024 (pushed stacked PR #2, head `79bc7f3`):
- `python3 tools/test_adaptation.py`: 13/13 passed.
- `python3 tools/verify_static.py`: 68/68 passed.
- `python3 tools/verify_offline.py`: 20/20 passed.
- `python3 tools/adapt_generated_artifact.py --check web-games/car-traffic
  web-games/flappy web-games/paddle-game`: all passed.
- `python3 tools/verify_pilot.py` against the CheerpJ CDN: 54/54 **local** checks passed;
  generated games, Paddle Range dependency, Snake first-input repaint, Stop, and
  Back verified.
- `python3 tools/adapt_generated_artifact.py --check` also passed against the two
  real local SwingJS source artifacts and a fresh unverified source build.
- Hosted project-2024 PR #2 CI [run 45106974783](https://github.com/AsistenProvikom/project-2024/actions/runs/45106974783) passed both jobs; PR #1 CI [run 44885053659](https://github.com/AsistenProvikom/project-2024/actions/runs/44885053659) passed both jobs.

## Current Task

Complete Milestone 6 hardening while manual legacy acceptance remains blocked.

1. Run the newly added source-staging and annotation-processing tests and obtain
   fresh CI results on PR #5; keep browser verification limited to trusted source.
2. Review PR #5 and PR #1 as separate code-merge decisions. PR #2 is stacked
   on PR #1; retarget/revalidate it only after the base merges.
3. Do not enable `PILOT_RELEASE_APPROVED`, publish a SwingJS runtime, or infer
   student JAR redistribution rights. B-001 through B-005 remain open.
4. Refresh live status from PRs and CI; do not reuse this dated checkpoint as
   proof of a later release.

## Known Failures

- None in the existing CheerpJ path in this session.
- Local `java` is not on `PATH`; use the pinned toolchain under
  `build/swingjs-toolchain/jdk`.
- Hosted CI for the source adapter passed on prior head `f74cfa0`; inspect current PR head for fresh verification.
- Phase 3 could not use original project-2024 sources (B-001).
- Snake now shows a non-blank state after its first center click, but legacy
  gameplay remains unverified; Froggie, Minesweeper, and Pong still need manual
  acceptance (B-005).
