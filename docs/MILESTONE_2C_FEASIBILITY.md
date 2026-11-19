# Milestone 2C.0 - SwingJS / Java2Script Feasibility

## Decision

**CONDITIONAL GO** for a source-backed Java 8 Swing conversion path.

SwingJS/Java2Script successfully transpiled and ran the Milestone 2C.0 POC in
Chromium with no J2S annotations or JavaScript shims. The POC used a real
`JFrame`, `JPanel`, `Graphics2D`, `Swing Timer`, and keyboard controls. Browser
verification measured startup to visible canvas at **1.84 s** in a focused run;
the cold, instrumented three-run benchmark measured a **5.92 s median**.
CheerpJ rendered the same JAR correctly but was slower to start and transferred
more data.

The "conditional" part is material:

- SwingJS requires source; this milestone did **not** prove arbitrary JAR
  conversion, decompilation, or Java 22 downleveling.
- Only one small POC was converted. Real-game compatibility, audio, networking,
  file I/O, reflection, and threading remain unproven.
- Applications that use `KeyListener` directly will need a source adaptation to
  Swing key bindings, or another input bridge.
- The SwingJS/Java2Script licensing and distribution model requires review
  before shipping generated artifacts.
- The generated SwingJS site is **28.8 MB on disk**, even though this POC only
  fetched **2.58 MB** over the network.

Proceed to 2C.1 only for Java 8 Swing projects with available source. Keep
CheerpJ as the fallback and default for JAR-only inputs.

## Scope

In scope:

1. Build an unmodified-API Java 8 Swing POC and transpile it with Java2Script.
2. Run it in headless Chromium with functional evidence from Java application
   state, not JavaScript assertions.
3. Verify desktop Swing behavior separately.
4. Benchmark the same JAR under SwingJS and CheerpJ.
5. Document the toolchain, supported subset, licensing, and next-step decision.

Out of scope:

- Decompiling arbitrary JARs.
- Downleveling Java 9+ bytecode or source.
- Converting the seven `project-2024` games.
- Audio, network, filesystem, reflection, thread, or JavaFX/SWT compatibility.
- Production `SwingJSAdapter` integration.
- Changing the production CheerpJ adapter.
- TeaVM work or gallery publishing.

## What Was Built

### POC

`examples/swing-poc/` is a Java 8 source project:

- 720x540 `JFrame` containing a `JPanel`.
- 20 ms `Swing Timer` animation with a moving circle.
- `Graphics2D` rendering with grid, circle, HUD, and direction indicator.
- Arrow-key direction changes, Space/P pause, and R reset.
- Java `System.out` `STATE` lines used as machine-readable application state.
- No SwingJS imports, annotations, or JavaScript bridge.
- No CheerpJ-specific code.

Keyboard handling uses Swing key bindings registered through
`getInputMap(JComponent.WHEN_IN_FOCUSED_WINDOW)` and `ActionMap`. This is
ordinary Java Swing code and required no transpiler-specific source changes.
The evidence therefore records `source_modifications_for_swingjs: 0`.

`examples/swing-poc/test/poc/DesktopSmokeTest.java` exercises direction, pause,
and reset directly and captures a `paintAll` screenshot. It exits nonzero on
failure so the build cannot hang on desktop verification.

### Build and Verification Tooling

- `tools/swingjs/build_swingjs_poc.py`
  - Builds a small Eclipse application that imports the POC and triggers the
    Java2Script JDT compilation participant.
  - Packages the generated SwingJS site and a comparable `SwingPoc.jar`.
  - Runs the desktop smoke test.
  - Produces `build/swingjs-poc/site/poc_SwingPoc.html` and
    `build/swingjs-poc/SwingPoc.jar`.
- `tools/swingjs/verify_swingjs_poc.py`
  - Serves the artifact and drives headless Chromium with Playwright.
  - Parses the Java application's own `STATE` output.
  - Verifies canvas size, animation, nonblank `Graphics2D` content, horizontal
    and vertical keyboard input, pause, and reset.
  - Writes `docs/verification/swingjs-poc.json`.
- `tools/swingjs/benchmark_swingjs.py`
  - Runs SwingJS and CheerpJ from the same POC JAR and 720x540 display.
  - Uses three alternating, fresh-browser runs and reports medians.
  - Measures CDP network bytes, canvas timing, first Java state, JS heap, and
    screenshot statistics.
  - Writes `docs/verification/swingjs-benchmark.json`.
- `tools/swingjs/cheerpj-harness/`
  - Minimal CheerpJ 5.0 wrapper used only for benchmarking.
  - Loads the runtime from the official CDN and auto-starts `poc.SwingPoc`.
  - Served through `provikom_converter.server.RangeRequestHandler`; CheerpJ
    refuses to load a JAR from a server without HTTP Range support.

Generated build output is under `build/` and is intentionally not committed.
External JDK, Eclipse, and Java2Script runtime inputs are also not committed.

### Toolchain

Tested versions:

| Component | Version / revision |
|---|---|
| JDK | 17.0.21.1+2 (Temurin) |
| Eclipse | 2024-03, IDE for Java Developers |
| Java2Script | `BobHanson/java2script` `4091b28` |
| J2S Eclipse plug-in | `5.0.1` |
| SwingJS runtime | `5.0.1-v7` |
| POC source/target | Java 8 |

Java2Script is an Eclipse JDT compilation participant, not a standalone
command-line compiler. The build script intentionally requires an Eclipse
installation and the `j2s.core.jar` drop-in. See "Reproduce" below.

## Functional Evidence

Desktop build verification passed. The browser verifier passed every check:

| Check | Result |
|---|---|
| Canvas mounted | 720x540 |
| Swing Timer animates | Passed |
| `Graphics2D` content nonblank | Passed |
| Horizontal keyboard input | Passed (`dx` changed) |
| Vertical keyboard input | Passed (`dy` changed) |
| Pause | Passed |
| Reset | Passed |

Focused verifier run:

- Startup to visible canvas: **1.84 s**
- First Java `STATE` with `ticks > 0`: **2.29 s**
- Artifact size: **28,810,518 bytes** in **3,730 files**
- Network payload: **2,567,371 bytes** in **237 requests**
- JS heap used: **18.2 MB**
- Canvas visual: `unique_colors=296`, `luminance_stddev=11.929`

The verifier parses `STATE` from the SwingJS `System.out` pane, so the timer,
movement, pause, and reset assertions come from the Java application rather
than a JavaScript test shim.

Known nonfatal warning: SwingJS requests `swingjs/j2s/core/package.js` and logs
a 404 as an ignored loader warning. Adding an empty `package.js` is not a fix;
it causes `ReferenceError: OK is not defined`. The artifact works with the
warning.

Screenshots:

- `docs/screenshots/swingjs-poc.png` - verified SwingJS POC.
- `docs/screenshots/swingjs-benchmark.png` - benchmark run.
- `docs/screenshots/cheerpj-benchmark.png` - same JAR under CheerpJ.

Both backends render the same app content and 720x540 canvas. Window chrome
differs: SwingJS uses an HTML-like frame, while CheerpJ uses its own title bar.

## SwingJS vs CheerpJ Benchmark

Method:

- Same `SwingPoc.jar`.
- Same 720x540 display and 1280x900 browser viewport.
- Both auto-start to avoid conflating startup with a user click.
- Three runs per backend in alternating order.
- Fresh browser context for each run.
- Timings are medians; ranges are in the evidence JSON.
- `startup` means navigation to a visible 720x540 canvas.
- `first Java state` means the first parsed `STATE` line with `ticks > 0`.
- Network bytes are Chromium CDP `Network.loadingFinished` encoded bytes.
- Local artifact size excludes the CheerpJ CDN runtime.

| Metric | SwingJS | CheerpJ | CheerpJ / SwingJS |
|---|---:|---:|---:|
| Startup to canvas | 5.92 s (5.85-6.39) | 19.99 s (11.40-20.00) | 3.38x |
| First Java state | 6.14 s (6.06-6.61) | 23.66 s (14.86-27.61) | 3.85x |
| First-load network | 2.58 MB / 226 requests | 17.10 MB / 121 requests | 6.63x |
| Local artifact | 28.81 MB / 3,730 files | 0.0064 MB / 3 files | - |
| JS heap used | 18.2 MB | 86.4 MB | 4.7x |

`performance.memory.usedJSHeapSize` covers the JavaScript heap only. CheerpJ
also uses WebAssembly/C++ memory that is not included, so this row is not a
total-memory comparison and likely understates CheerpJ's footprint.

The focused verifier observed faster SwingJS startup (1.84 s) than the
benchmark. The benchmark is the conservative head-to-head comparison: it starts
a new Chromium process for every run, enables CDP network instrumentation, and
uses a fresh browser context. CheerpJ timing varied widely because its 17.1 MB
runtime is fetched from the external CDN; the fastest observed startup was
11.4 s. Do not treat the CheerpJ median as a fixed runtime constant.

Interpretation:

- SwingJS startup and first-state latency were substantially better on this
  POC, and the browser transferred much less data on first load.
- SwingJS requires deploying a **28.8 MB** static site. It does not depend on a
  third-party CDN at runtime.
- CheerpJ has a tiny local artifact but brings a **17.1 MB** external runtime
  download, higher JS heap use, and CDN variability.
- These results are for one small POC and must not be generalized to the
  `project-2024` games without measurement.

## Compatibility Findings

Observed working:

- `JFrame`, `JPanel`, layout/pack, and window activation.
- `Graphics2D` fills, strokes, text, and antialiasing used by the POC.
- `Swing Timer` and animation.
- Swing key bindings with `WHEN_IN_FOCUSED_WINDOW`.
- Java `System.out` output exposed through the SwingJS output pane.

Observed limitation:

- A `KeyListener` attached to the panel did not receive browser key events in
  the generated SwingJS app. Adding the listener in the constructor or later in
  `addNotify()` did not fix it. Swing key bindings did work.
- This matters for real games: a source project that polls or listens with
  `KeyListener` may need a mechanical migration to `InputMap`/`ActionMap` or a
  supported browser input bridge. That adaptation must be counted as a source
  change in 2C.1.
- The POC's zero source modifications does not mean every Swing app needs zero;
  the POC was authored with key bindings from the start.

Not tested:

- Audio and MIDI.
- `KeyListener` migration across multiple components.
- Full-screen, focus, and DPI/scale variations.
- Nested windows, dialogs, menus, and popups.
- Java 9+ source or bytecode.
- Real-game graphics, assets, loops, or frame pacing.
- Long-running stability, memory growth, and recovery.
- Security behavior for untrusted source projects.

## Licensing and Distribution

Findings from the tested Java2Script/SwingJS tree:

- `java2script/LICENSE.txt` states GPL v2 with the Classpath Exception,
  describing it as formerly EPL 1.0.
- `Java2ScriptVisitor.java` carries an EPL 1.0 header.
- The bundled JSON library includes the "Good, not Evil" JSON license.
- The generated site bundles SwingJS runtime/class files and the JSON license,
  but does not include a top-level Java2Script license/notice file.

This project's MIT license does not relicense Java2Script, SwingJS, Eclipse,
the JDK, or CheerpJ. Before distributing generated SwingJS artifacts, the
project needs a deliberate licensing review covering the generated output,
runtime redistribution, notices, and Classpath Exception obligations. This
report is not legal advice.

The build currently uses external toolchains and does not vendor the Java2Script
runtime into the repository. A production 2C.1 pipeline must pin artifact
hashes and decide which runtime files, notices, and licenses are shipped.

## Risks and Open Questions

1. **Source-only input.** SwingJS cannot consume a JAR directly. This milestone
   did not authorize decompilation.
2. **Real-game coverage.** One POC is not evidence for the seven fixtures or
   for arbitrary NetBeans projects.
3. **Host execution.** The desktop smoke test executes the app on the host.
   That is acceptable for a trusted POC but conflicts with the project's
   zero-execution posture for untrusted games. 2C.1 must sandbox or omit host
   execution.
4. **Input migration.** `KeyListener`-based games need a source adaptation.
5. **Artifact weight.** 28.8 MB per deployed site may be unacceptable for a
   gallery; caching and shared runtime hosting need evaluation.
6. **Licensing.** GPLv2+CPE/EPL and JSON-license obligations require review.
7. **Toolchain reproducibility.** Eclipse, J2S, and the runtime are external
   inputs. CI must pin versions/hashes and avoid `/tmp` assumptions.
8. **CheerpJ comparison scope.** CheerpJ's CDN timing is variable and its
   production adapter waits for a user gesture. The benchmark auto-starts both
   backends and is not a full user-perceived performance model.
9. **Java version.** Java 8 is the only tested source target. Java 22
   downleveling is explicitly out of scope.

## Proposed 2C.1

**Source-backed SwingJS adapter, with CheerpJ fallback.**

1. Accept a Java 8 source project, not a JAR. Reject bytecode-only inputs with
   a clear "source required" result.
2. Run a pinned, containerized Eclipse/Java2Script build with no host
   application execution and no network access except pinned downloads.
3. Emit a self-contained static artifact with a manifest and lifecycle state,
   matching the existing CheerpJ artifact conventions where practical.
4. Add functional gates: desktop-free compile/transpile, browser canvas,
   `STATE`-driven animation/input checks, nonblank rendering, and screenshots.
5. Treat `KeyListener` to key-binding migration as an explicit, auditable
   transformation; never silently rewrite game source.
6. Keep CheerpJ as the fallback whenever transpilation or verification fails.
7. Resolve licensing/notice requirements before publishing generated artifacts.
8. Start with one trusted Java 8 Swing fixture with available source and report
   exact support limits. Do not claim general JAR conversion.
9. Defer decompilation, Java 9+ downleveling, audio, TeaVM, and gallery work.

## Reproduce

Prerequisites: Python 3.9+, JDK 17+, Eclipse 2024-03, Java2Script at the
reviewed revision, Playwright Chromium, and Pillow.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[browser]'
python3 -m playwright install chromium

git clone https://github.com/BobHanson/java2script.git /tmp/java2script
git -C /tmp/java2script checkout 4091b28

export PROVIKOM_JAVA_HOME=/path/to/jdk-17
export PROVIKOM_ECLIPSE_HOME=/path/to/eclipse
export PROVIKOM_SWINGJS_SITE_ZIP=/tmp/java2script/sources/net.sf.j2s.core/dist/swingjs/SwingJS-site.zip

# Copy /tmp/java2script/sources/net.sf.j2s.core/dist/swingjs/j2s.core.jar
# into $PROVIKOM_ECLIPSE_HOME/dropins/ before building.

python3 tools/swingjs/build_swingjs_poc.py --require-desktop
python3 tools/swingjs/verify_swingjs_poc.py
python3 tools/swingjs/benchmark_swingjs.py --runs 3
```

`--require-desktop` needs a display or Xvfb; pass `--xvfb /path/to/Xvfb` when
needed. The build command above was run successfully on the tested toolchain
and produced `28,810,518` bytes in `3,730` files.

Project regression checks run for this milestone:

```bash
PROVIKOM_GAMES_DIR=/path/to/project-2024/games \
PROVIKOM_REQUIRE_FIXTURES=1 PROVIKOM_SKIP_BROWSER=1 \
python3 -m unittest discover -s tests -v
# Ran 99 tests, OK (4 browser tests skipped)

PROVIKOM_GAMES_DIR=/path/to/project-2024/games \
PROVIKOM_REQUIRE_FIXTURES=1 PROVIKOM_REQUIRE_BROWSER=1 \
python3 -m unittest discover -s tests -v
# Ran 105 tests, OK
```

## Evidence Files

- `docs/verification/swingjs-poc.json` - functional browser evidence.
- `docs/verification/swingjs-benchmark.json` - three-run benchmark, medians,
  per-run values, network and memory data.
- `docs/screenshots/swingjs-poc.png` - verified SwingJS POC.
- `docs/screenshots/swingjs-benchmark.png` - SwingJS benchmark screenshot.
- `docs/screenshots/cheerpj-benchmark.png` - CheerpJ benchmark screenshot.
- `examples/swing-poc/` - Java 8 POC and desktop smoke test.
- `tools/swingjs/` - build, verification, benchmark, and CheerpJ harness.
