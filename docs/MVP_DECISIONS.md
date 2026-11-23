# Provikom MVP Decisions

## D-001: Keep CheerpJ as the default for compiled JARs

CheerpJ is the only verified path for JAR-only inputs. SwingJS requires source
and must not be presented as a JAR decompiler.

## D-002: Treat SwingJS as a constrained source backend

The supported input is Java 8 source for Swing projects with a discoverable
`public static void main`. Unsupported APIs, Java 9+ source, and missing
dependencies are reported as blockers rather than silently transformed.

## D-003: Reuse the pinned Java2Script pipeline

The Eclipse JDT compilation participant, pinned JDK/Eclipse, Java2Script
compiler, and SwingJS runtime from Milestone 2C.0 remain authoritative. The
production adapter must call reusable code rather than introducing a second
unrelated transpiler.

## D-004: Produce standard Provikom artifact layout

The new source-backed artifact should expose `index.html` and `manifest.json` at
its root so the portal can serve it below a subdirectory without manual path
rewriting. Build logs, source hashes, and toolchain evidence are separate from
the runtime entry point.

## D-005: Do not distribute SwingJS runtime artifacts yet

Generated sites can be built and tested locally/CI. Licensing and notice
obligations remain unresolved; build output stays ignored and publication is
blocked.

## D-006: Stack work when a prior PR is unmerged

Project 2024 PR #1 remains an approval checkpoint. Converter work proceeds
independently on `milestone-2c1-swingjs-source-adapter`. Any portal changes that
depend on unmerged converter output will be documented as stacked branches.

## D-007: Validate, do not rewrite, SwingJS source artifacts for the portal

Source-backed artifacts use a root-level `index.html`, relative runtime URLs,
and an empty SwingJS `serverURL`. The project-2024 publishing step therefore
validates ownership, generated-JavaScript integrity, and path safety, then
leaves the artifact unchanged. Only CheerpJ artifacts retain the tested
`/app/` -> `/str/` compatibility bridge. This keeps regeneration idempotent and
avoids introducing a second manual rewrite for source artifacts.
