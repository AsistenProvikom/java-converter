# SwingJS Source Adapter (Milestone 2C.1)

## Purpose

The SwingJS adapter converts explicitly supported Java 8 Swing **source**
projects into browser-playable static artifacts. It does not decompile JARs and
does not claim compatibility for arbitrary Java games.

The reusable implementation lives in `provikom_converter/swingjs/`; the prior
Milestone 2C.0 scripts under `tools/swingjs/` remain feasibility/reproduction
tools.

## Supported Input

A project must have this layout:

```text
<project>/
└── src/
    └── **/*.java
```

Requirements:

- Java source with a discoverable `public static void main(String[])` or
  `main(String...)`.
- Exactly one main class, unless `--main-class` selects one.
- Files are UTF-8 and do not use Java module descriptors (`module-info.java`).
- Source files and path components are not symlinks.
- No JavaFX or SWT imports.
- Dependencies must be available as source in the same `src/` tree. External
  `lib/*.jar` dependencies are not transpiled or staged.

Detected but unverified APIs are recorded as warnings, including audio,
filesystem, networking, reflection, threading, `KeyListener`, and `Robot`.
Audio imports mark the artifact as having audio and require manual browser
review.

## CLI

```bash
python3 tools/swingjs/setup_toolchain.py

python3 -m provikom_converter build-project examples/swing-poc \
  --backend swingjs \
  --output ./build/swingjs-poc-adapter

python3 -m provikom_converter verify-swingjs ./build/swingjs-poc-adapter \
  --evidence ./build/swingjs-poc-adapter/verification.json \
  --screenshot ./build/swingjs-poc-adapter/verification.png
```

Useful build options:

| Option | Meaning |
|---|---|
| `--title` | Override the display title. |
| `--main-class` | Select one entry point when several exist. |
| `--toolchain-dir` | Point at a managed pinned toolchain. |
| `--java-home`, `--eclipse-home`, `--site-zip` | Explicit pinned components for diagnostics. |
| `-f`, `--force` | Replace only a valid Provikom artifact or empty directory. |

The toolchain can also be selected with `PROVIKOM_SWINGJS_TOOLCHAIN`.

## Build Pipeline

1. Validate the source project and compute a deterministic source hash.
2. Resolve the pinned toolchain and verify the SwingJS runtime and Java2Script
   compiler SHA-256 values.
3. Copy the original source into an isolated build workspace without modifying
   it.
4. Compile all source with the pinned JDK 17 `javac --release 8`.
5. Compile and install the packaged headless Eclipse Java2Script builder plugin.
6. Extract the pinned `SwingJS-site.zip` runtime into the artifact workspace.
7. Run headless Eclipse/Java2Script and require explicit build-success markers.
8. Locate the generated HTML entry and JavaScript for the selected main class;
   reject missing or implausibly small output.
9. Copy the site into a root-level standard artifact, sanitize `index.html`,
   remove the external SwingJS server URL, and add the hidden `#sysoutdiv`
   state pane.
10. Write `manifest.json`, ownership marker, build evidence, and publish
    atomically.

The original source tree is preserved. Build workspaces use temporary
directories and are removed afterwards.

## Artifact Layout

```text
<artifact>/
├── index.html
├── manifest.json
├── .provikom-artifact.json
├── swingjs/                    # Pinned runtime and generated j2s files
├── evidence/
│   ├── build.json
│   ├── eclipse.log
│   ├── javac-plugin.log
│   ├── javac-sources.log
│   ├── jar-plugin.log
│   └── runtime-extract.log
├── verification.json           # After verify-swingjs succeeds
└── verification.png
```

`manifest.json` is schema `1.1` with `backend: "swingjs"` and includes:

- `source_project`: main class, source SHA-256, file hashes, source count,
  generated JavaScript path/hash, and original generated entry template.
- `runtime` and `toolchain`: pinned JDK/Eclipse/Java2Script/SwingJS versions and
  hashes.
- `compatibility`: static prediction, never rewritten as execution evidence.
- `lifecycle`: initially `built`, updated only from browser verification.
- `ownership`: marker name and artifact ID, bound to the manifest hash.
- `generated_files`: paths required by artifact ownership validation.

The build does not copy `SwingPoc.jar`, decompile classes, or claim host-side
execution.

## Browser Verification

`verify-swingjs` serves the artifact on `127.0.0.1`, opens it in headless
Chromium, and requires:

- canvas mounted at a plausible size;
- non-blank canvas pixels (color diversity, luminance variance, non-dark ratio);
- HTTP 200 for the generated application JavaScript;
- no page errors, failed requests, or fatal console messages.

When the artifact exposes the POC-style `STATE x=... ticks=...` pane, it also
requires Swing Timer advancement, horizontal and vertical arrow direction,
pause persistence, and reset.

A second fixture protocol is also supported: applications may print
`FIXTURE ticks=N clicks=N phase=F running=BOOL`. The verifier then requires
timer advancement and a mouse click that increments the application's click
counter. This is opt-in application state, not a JavaScript shim. Unrelated
applications receive only the generic canvas/graphics/JavaScript checks.

The record is written to `verification.json`, the manifest lifecycle becomes
`runtime_verified` only on success, and the ownership marker is refreshed.

## Rejections and Diagnostics

Examples of actionable errors:

- missing `src/` or no `.java` files;
- no main method or multiple main classes without `--main-class`;
- JavaFX/SWT imports;
- symlinked source paths;
- missing, incomplete, or checksum-mismatched pinned toolchain;
- source compilation failure with the last compiler output;
- Eclipse/Java2Script failure without `PROVIKOM_BUILD_OK` or transpile markers;
- missing generated entry/JavaScript or generated output too small to trust;
- unsafe output paths, or `--force` against unrelated data.

## Security and Licensing

- Source paths, output paths, and symlink components are validated before any
  replacement.
- The temporary Eclipse workspace copies only inspected `src/**/*.java`
  files, not the entire input directory. Non-Java files, Git metadata, binary
  resources and unrelated symlinks are excluded. Additional assets/resources
  are outside the current supported input contract.
- Source `javac --release 8 -proc:none` disables annotation processor discovery
  during the initial Java compilation step.
- **Trust boundary:** These checks are defense in depth, not an execution
  sandbox. Native JDK/Eclipse tooling is run and Chromium verification uses
  `--no-sandbox` in CI. Only process trusted, reviewed Java source in a
  disposable, isolated worker. Do not expose these CLI commands as a public
  untrusted-code build service without a separately reviewed sandbox.
- Runtime ZIP extraction rejects absolute paths and parent traversal.
- The artifact is validated against source and generated-JavaScript hashes.
- Generated SwingJS sites stay under ignored `build/` directories and are not
  published. See `docs/SWINGJS_LICENSING.md` for unresolved distribution
  obligations.

## Current Evidence

Two independent fixtures built and verified locally:

| Fixture | Main class | Checks |
|---|---|---|
| `examples/swing-poc` | `poc.SwingPoc` | canvas, graphics, generated JS, timer, arrows, pause, reset |
| `examples/swing-widgets` | `compat.WidgetDemo` | canvas, graphics, generated JS, timer, mouse click |

The widget fixture also exercises `BorderLayout`, `JButton`, `JLabel`, and
`MouseAdapter`. Both artifacts passed ownership validation after build and
verification. Evidence:

- `docs/verification/swingjs-adapter-poc.json`
- `docs/verification/swingjs-widgets.json`
- `docs/screenshots/swingjs-adapter-poc.png`
- `docs/screenshots/swingjs-widgets.png`

Generated Java2Script wall-clock comments are normalized to a fixed marker.
Two clean builds of the same source tree produce identical generated JavaScript
bytes. Source artifacts also use root-relative URLs, so the project-2024
publishing check validates their ownership and hashes and leaves them unchanged
instead of applying the CheerpJ `/app/` -> `/str/` bridge.

See `docs/MILESTONE_3_COMPATIBILITY.md` for API and limitation details.

No original project-2024 Java sources are available, so this does not establish
compatibility for the seven portal games. See `docs/MVP_BLOCKERS.md`.
