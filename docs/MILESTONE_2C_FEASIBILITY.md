# Milestone 2C.0 - SwingJS / Java2Script Feasibility

## Decision

**CONDITIONAL GO** for a source-backed Java 8 Swing conversion path.

SwingJS/Java2Script successfully transpiled and ran the Milestone 2C.0 POC in
Chromium with no J2S annotations or JavaScript shims. The POC used a real
`JFrame`, `JPanel`, `Graphics2D`, `Swing Timer`, and keyboard controls. Browser
verification measured startup to visible canvas at **2.01 s** in a focused run;
the cold, instrumented three-run benchmark measured a **5.95 s median**.
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
  fetched roughly **2.6 MB** over the network in focused verification.

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

- `tools/swingjs/setup_toolchain.py`
  - Downloads the pinned JDK and Eclipse archives.
  - Rejects archives whose size or SHA-256 does not match the manifest.
  - Fetches the exact Java2Script commit, verifies the compiler JAR and runtime
    ZIP hashes, and installs the Eclipse plug-in into an ignored toolchain
    directory.
  - Writes `build/swingjs-toolchain/toolchain.json`.
- `tools/swingjs/toolchain_manifest.json`
  - Machine-readable pins for versions, URLs, revisions, sizes, and hashes.
- `tools/swingjs/build_swingjs_poc.py`
  - Resolves the managed toolchain by default; explicit paths remain supported.
  - Verifies the managed runtime and compiler hashes before building.
  - Builds a small Eclipse application that imports the POC and triggers the
    Java2Script JDT compilation participant.
  - Packages the generated SwingJS site and a comparable `SwingPoc.jar`.
  - Runs the desktop smoke test.
  - Rejects missing or implausible generated JavaScript, then records its size,
    SHA-256, and source-derived markers in `toolchain.json`.
  - Produces `build/swingjs-poc/site/poc_SwingPoc.html` and
    `build/swingjs-poc/SwingPoc.jar`.
- `tools/swingjs/verify_swingjs_poc.py`
  - Serves the artifact and drives headless Chromium with Playwright.
  - Parses the Java application's own `STATE` output.
  - Verifies canvas size, animation, nonblank `Graphics2D` content, horizontal
    and vertical keyboard input, pause, and reset.
  - Writes `docs/verification/swingjs-poc.json` by default, or a caller-chosen
    evidence path for CI.
  - Measures network bytes with CDP, separately from artifact disk size.
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

### Pinned Toolchain

Versions and SHA-256 values are defined in
`tools/swingjs/toolchain_manifest.json` and enforced by the setup script.

| Component | Version / revision | SHA-256 |
|---|---|---|
| Temurin JDK archive | 17.0.21.1+2 | `0b0ac5eab6db6abaec68c9913bcddb31321e5da411c45073d520d9c125e6f7b4` |
| Eclipse Java IDE archive | 2024-03 R (4.31.0) | `f16a8714bcb06105edcd41b1055b2dc46a95539e561e8029667c99eaeaf85e05` |
| Java2Script compiler | `4091b28`, J2S `5.0.1` | `81dbd7dbbc1f9eff90d3a47c48d3625b135ab8c3a12345d491f41a0bc6dbd76a` |
| SwingJS runtime | `5.0.1-v7` | `2b275f7c1bbd420aa79a5831a1fd2d9e4b3dd75079f0f2eb8fe29d13e0d4cec0` |
| Java2Script license | commit `4091b28` | `b3bffcae3b9483cb91aefb6a4fb2fcacef8f9ac5bf7ac505000bc1b7a2a2ed5e` |
| POC source/target | Java 8 | Source hash recorded per build |

The Eclipse archive's SHA-256 was computed from the archive whose SHA-512
matches Eclipse's published `.sha512` value
`973c94a0a029c29d717823a53c3a65f99fa53d51f605872c5dd854620e16cd4cb2c2ff8a5892cd550a70ab19e1a0a0d2e792661e936bd3d2bef4532bc533048b`.
The JDK SHA-256 matches Adoptium's published `.sha256.txt` asset.

Java2Script is an Eclipse JDT compilation participant, not a standalone
command-line compiler. The setup script fetches the exact commit, sparse
checkouts the compiler/runtime distribution, verifies the artifacts, and
installs the `j2s.core.jar` drop-in. No downloaded archive is committed.

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

Focused verifier run (local, fresh browser):

- Startup to visible canvas: **2.01 s**
- First Java `STATE` with `ticks > 0`: **2.51 s**
- Artifact size: **28,810,518 bytes** in **3,730 files**
- Network payload: **2,613,071 bytes** in **237 requests**
- JS heap used: **17.1 MB**

These numbers are single-run observations. The benchmark section below is the
more conservative, repeated comparison. CI writes a separate evidence file
under `build/swingjs-poc/verification.json` so it does not rewrite committed
documentation.

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

## Generated Artifact Layout

The ignored build tree separates the downloadable toolchain, build evidence,
and the deployable site:

```text
build/
├── swingjs-toolchain/
│   ├── downloads/                 # verified JDK/Eclipse archives
│   ├── jdk/
│   ├── eclipse/                   # J2S plug-in installed in dropins/
│   ├── java2script/               # sparse, pinned Java2Script checkout
│   └── toolchain.json             # versions, hashes, absolute paths
└── swingjs-poc/
    ├── SwingPoc.jar               # compiled Java 8 POC
    ├── classes/
    ├── desktop-poc.png
    ├── desktop-smoke.log
    ├── eclipse.log
    ├── javac-poc.log
    ├── toolchain.json             # build + generated-JS evidence
    ├── verification.json          # CI-only if --evidence is redirected
    ├── verification.png           # CI-only if --screenshot is redirected
    ├── work/                      # Eclipse workspace and imported project
    └── site/                      # deployable static site candidate
        ├── poc_SwingPoc.html
        └── swingjs/
            ├── j2s/poc/SwingPoc.js
            └── j2s/...            # SwingJS runtime/class library
```

Only `site/` is a deployment candidate. It is currently a local/CI test
artifact because the runtime licensing and notice obligations are unresolved.
The complete site is not committed and is not uploaded by CI.

## GitHub Actions Reproduction

`.github/workflows/swingjs-feasibility.yml` provisions the pinned toolchain on
an ephemeral `ubuntu-22.04` runner, transpiles the POC with headless Eclipse,
asserts that the generated JavaScript contains the transpiled class and state
output, runs Playwright verification, and asserts the machine-readable result
is `runtime_verified`.

The workflow uploads logs, hashes, screenshots, verification JSON, and the
small generated POC HTML/JavaScript. It deliberately does not upload the
SwingJS runtime/site. CI results are recorded in the pull request and below
after the clean-runner execution completes.

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
| Startup to canvas | 5.95 s (5.78-6.01) | 11.19 s (11.16-13.49) | 1.88x |
| First Java state | 6.17 s (6.00-6.23) | 14.43 s (14.01-16.84) | 2.34x |
| First-load network | 2.58 MB / 226 requests | 17.10 MB / 121 requests | 6.63x |
| Local artifact | 28.81 MB / 3,730 files | 0.0064 MB / 3 files | - |
| JS heap used | 18.2 MB | 86.4 MB | 4.7x |

`performance.memory.usedJSHeapSize` covers the JavaScript heap only. CheerpJ
also uses WebAssembly/C++ memory that is not included, so this row is not a
total-memory comparison and likely understates CheerpJ's footprint.

The focused verifier observed faster SwingJS startup (2.01 s) than the
benchmark. The benchmark is the conservative head-to-head comparison: it starts
a new Chromium process for every run, enables CDP network instrumentation, and
uses a fresh browser context. CheerpJ timing varied widely between sessions
because its 17.1 MB runtime is fetched from the external CDN: this run ranged
from 11.2 s to 13.5 s, while an earlier run observed about 20 s. Do not treat
the CheerpJ median as a fixed runtime constant or generalize the ratios.

Interpretation:

- SwingJS startup and first-state latency were better on this POC, and the
  browser transferred much less data on first load. The latency margin varied
  by session because CheerpJ's CDN runtime dominates its startup.
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

The root Java2Script license is GPLv2 with the Classpath Exception, but the
tested tree also contains EPL 1.0 file headers, Apache 2.0/Apache Harmony
material, OpenJDK-derived code, and the JSON.org license. The generated site
currently ships the JSON license but not the Java2Script root license, Apache
Harmony NOTICE, or Apache 2.0 text.

The project's MIT license does not relicense any of those components or
CheerpJ. Redistribution rights for the generated site remain unresolved. The
current policy is therefore:

- Keep all generated sites under ignored `build/` directories.
- Do not commit or upload the complete SwingJS runtime/site.
- CI uploads only logs, hashes, the small source-derived POC JavaScript/HTML,
  screenshots, and verification records.
- Do not publish a SwingJS demo or gallery artifact until a distribution
  review is complete.

See [SWINGJS_LICENSING.md](SWINGJS_LICENSING.md) for the component-level review,
hashes, required notices, and open questions. This is an engineering review,
not legal advice.

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
6. **Licensing.** GPLv2+CPE/EPL/Apache/JSON obligations require review and a
   generated NOTICE/SBOM before distribution.
7. **Toolchain reproducibility.** Local setup is now pinned and can be
   executed from a clean checkout. Hosted CI reproduction still has to be
   observed and recorded before this risk is closed.
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

Prerequisites: Python 3.9+, `git`, `tar`, `unzip`, Playwright Chromium, Pillow,
and network access to the pinned JDK/Eclipse/Java2Script sources. The JDK and
Eclipse installations are provisioned by the setup script; a system JDK is not
required.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[browser]'
python3 -m playwright install chromium

python3 tools/swingjs/setup_toolchain.py
python3 tools/swingjs/build_swingjs_poc.py --require-desktop
python3 tools/swingjs/verify_swingjs_poc.py
python3 tools/swingjs/benchmark_swingjs.py --runs 3
```

The toolchain is installed under `build/swingjs-toolchain`. The build script
discovers it automatically; no `/tmp` path or machine-specific environment
variable is required. Override the destination with `--dest` and pass
`--toolchain-dir` to the build script if a different location is used.

A clean-destination run downloaded both archives from the pinned URLs, verified
their hashes, sparse-checked out the exact Java2Script commit, and built and
verified the artifact without a pre-populated cache. Re-running setup with the
same pinned manifest reuses the verified archives and extracted trees.

`--require-desktop` needs a display or Xvfb; pass `--xvfb /path/to/Xvfb` when
needed. The build command above was run successfully on the tested toolchain
and produced `28,810,518` bytes in `3,730` files.

CI runs the same steps in
`.github/workflows/swingjs-feasibility.yml`, from a clean checkout, using
`xvfb-run`. The workflow asserts that the generated JavaScript contains the
transpiled `SwingPoc` class and the Java state output, then runs browser
verification and approves only `runtime_verified` evidence.

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
- `docs/SWINGJS_LICENSING.md` - component-level licensing review.
- `.github/workflows/swingjs-feasibility.yml` - clean-runner reproduction.
- `docs/screenshots/swingjs-poc.png` - verified SwingJS POC.
- `docs/screenshots/swingjs-benchmark.png` - SwingJS benchmark screenshot.
- `docs/screenshots/cheerpj-benchmark.png` - CheerpJ benchmark screenshot.
- `examples/swing-poc/` - Java 8 POC and desktop smoke test.
- `tools/swingjs/` - build, verification, benchmark, and CheerpJ harness.
