# Provikom MVP Execution Plan

Date: 2026-11-21
Owner: Converter engineering
Repositories:
- `AsistenProvikom/java-converter` (converter, authoritative implementation)
- `AsistenProvikom/project-2024` (portal integration)

## Goal

Deliver a maintainable Java-to-browser publishing system with two evidence-backed
paths:

1. **Path A: compiled JAR -> CheerpJ browser artifact.** Existing path; must
   preserve compatibility, safety, and reproducibility.
2. **Path B: supported Java 8 Swing source -> JavaScript artifact.** New
   SwingJS/Java2Script path for explicitly supported source projects only.

The MVP is engineering-complete only when the acceptance criteria below are
verified. Legal permission to publish is a separate approval gate.

## Non-goals

- Arbitrary JAR decompilation or arbitrary JAR-to-JavaScript conversion.
- Downleveling Java 9+ source or bytecode to Java 8.
- Claiming universal Swing compatibility from one POC.
- Publishing or deploying generated SwingJS runtime bundles before licensing
  review.
- Replacing the working legacy portal behavior.

## Milestone Definitions and Acceptance Criteria

| ID | Milestone | Repository | Acceptance criteria | Dependencies |
|---|---|---|---|---|
| 0 | Planning and tracking | java-converter | Plan, progress, decisions, and blocker records exist and are current. | none |
| 1 | Finalize Project 2024 Milestone 3A | project-2024 | PR #1 artifact ownership, manifests, `/str/` paths, lifecycle, legacy fallback, release gate, and CI verified; branch merge-ready; no merge/deploy performed. | none |
| 2 | SwingJS source adapter (2C.1) | java-converter | `provikom build-project <src> --backend swingjs -o <out>` performs real Java2Script transpilation of a supported Java 8 Swing project, preserves sources, safely handles output, produces a browser-playable artifact and machine-readable evidence, rejects unsupported input with actionable diagnostics, and keeps CheerpJ tests green. | 0 |
| 3 | Real-project compatibility testing | java-converter | Test a second source-backed Swing fixture and document APIs, input, animation, unsupported features, and required source changes. If original project-2024 sources are unavailable, record that explicitly and do not fabricate conversion. | 2 |
| 4 | Reproducible artifact publishing | both | Normal publishing does not require manual `/app/` -> `/str/` patching, or the remaining adapter step is a documented, tested compatibility bridge. Regeneration is idempotent, relative-path safe, Range-capable where required, and ownership markers stay valid. | 1, 2 |
| 5 | Project 2024 validation (3B) | project-2024 | All seven gallery entries have recorded build/launch/render/input/audio/error/limitation status. Snake blank rendering investigated. Pong audio limitation preserved. Legacy fallback retained. | 1, 4, 6 |
| 6 | Security, quality, and documentation | both | Cross-repository review covers paths, symlinks, archives, metadata, iframe boundaries, lifecycle, pinning, CI, Docker, diagnostics; installation, supported versions, backends, CLI, limitations, integration, security, licensing, and release docs are accurate. | all |

## Status Values

`NOT_STARTED` -> `IN_PROGRESS` -> `VERIFIED` -> `COMPLETE`; use `BLOCKED` when
an external dependency or missing input prevents progress. Code committed is not
`VERIFIED`; verification requires the stated commands and evidence.

## Repository Ownership

| Work item | Owner repository |
|---|---|
| SwingJS toolchain, adapter, CLI, compatibility reports | java-converter |
| Converter tests, evidence, licensing docs | java-converter |
| Generated portal artifacts and catalog status | project-2024 |
| Legacy gameplay validation | project-2024 |
| Release/deployment gate | project-2024 |

## Dependency Order

```text
0 planning
  |
1 PR #1 verification (approval checkpoint, no merge)
  |
2 SwingJS source adapter
  |
3 second-fixture compatibility testing
  |
4 publishing/integration improvement
  |
5 project-2024 validation (3B)
  |
6 final security/documentation review
```

## Verification Commands

Converter baseline:

```bash
cd java-converter
python3 -m unittest discover -s tests -v
python3 -m unittest tests.test_build tests.test_cli tests.test_build_safety -v
```

SwingJS MVP:

```bash
python3 tools/swingjs/setup_toolchain.py
provikom build-project examples/swing-poc --backend swingjs -o build/swingjs-adapter-poc
provikom verify-swingjs build/swingjs-adapter-poc --evidence build/swingjs-adapter-poc/verification.json
python3 tools/swingjs/verify_swingjs_poc.py --artifact-dir build/swingjs-poc
```

Project 2024:

```bash
cd project-2024
python3 tools/verify_static.py
python3 tools/test_adaptation.py
python3 tools/verify_offline.py
python3 tools/adapt_generated_artifact.py --check \
  web-games/car-traffic web-games/flappy web-games/paddle-game
```

CI is authoritative when local browser/toolchain dependencies are unavailable.

## PR and Checkpoint Links

- Project 2024 PR #1: https://github.com/AsistenProvikom/project-2024/pull/1
  - Head at start of MVP work: `6a17f89`
  - Status: OPEN, MERGEABLE, CI green, approval checkpoint only.
- java-converter MVP branch: `milestone-2c1-swingjs-source-adapter`
- java-converter PR: created after the first verified MVP commit set.

## Release Readiness Criteria

Engineering readiness requires all mandatory tests and CI checks to pass, no
open critical security defect, accurate documentation, and verified artifacts.
Publication additionally requires:

- SwingJS/Java2Script licensing and notice compliance.
- CheerpJ Community Edition usage approval.
- Permission to redistribute student JARs and generated artifacts.
- Manual legacy visual acceptance.
- `PILOT_RELEASE_APPROVED=true` set by an authorized human.

Engineering completion does not grant legal authorization to publish.

## Current Blockers

See `docs/MVP_BLOCKERS.md`.
