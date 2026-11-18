# Provikom Converter

[![Test Suite](https://img.shields.io/badge/tests-93%20passed-brightgreen.svg)]()
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()

**Provikom Converter** is an open-source Java game-to-web publishing tool. It analyzes Java game archives (compiled JARs, NetBeans projects) to assess browser compatibility across candidate runtimes and compilers (**CheerpJ**, **TeaVM**, **SwingJS**), and can generate playable CheerpJ 5.0 web artifacts without executing untrusted game code on the host.

---

## Key Capabilities (Milestones 1, 2A, and 2B)

- **Zero-Execution JVM Bytecode Analyzer**:
  - Direct binary parsing of classfile constant pools, attributes, and method signatures without invoking a local JVM.
  - Accurate class major version detection (Java 8 up to Java 25).
  - Framework detection: Swing, AWT, JavaFX, SWT.
  - API detection: Audio (`javax.sound.sampled`, MIDI), Threading, Direct File I/O, Network Sockets, Reflection.
  - NetBeans library dependency detection (e.g. `AbsoluteLayout.jar`).
- **Archive Ingestion Security**:
  - Zip-Slip path traversal prevention.
  - Zip-bomb and resource exhaustion guards (500 MB limit, 50,000 entry limit, ratio alarms).
  - Embedded archive discovery (detects nested JARs).
- **Backend Adapter Architecture**:
  - Independent adapter contracts for CheerpJ, TeaVM, and SwingJS.
  - Rigorous differentiation between *verified capabilities* and *runtime assumptions/risks*.
- **Standardized JSON Report Schema**:
  - Conforms to JSON Schema Draft-07 (`schema/compatibility-report.schema.json`).
  - Generates machine-readable JSON and human-readable terminal summaries.
- **CheerpJ 5.0 Playable Artifact Builder**:
  - One-command generation of a static HTML/CSS/JS game player from an unmodified JAR.
  - Automatic runtime selection: Java 8, Java 21 LTS, or the experimental Java 25 preview target for Java 22 bytecode.
  - Automatic staging and classpath registration of manifest `Class-Path` dependencies (for example `lib/AbsoluteLayout.jar`).
  - Official CheerpJ APIs (`cheerpjInit`, `cheerpjCreateDisplay`, `cheerpjRunMain`) with `/app/` asset mounting.
  - In-page loading, compatibility, and Java exception diagnostics.
  - Range-Request-capable local HTTP server for reliable JAR streaming.
- **Safe, Transactional Builds (Milestone 2B)**:
  - `--force` replacements are built in a temporary sibling directory and published only after a successful build.
  - Existing artifacts survive failed force rebuilds.
  - Output paths are rejected when they are the source JAR, its parent, an ancestor, a filesystem root, or a symlink.
- **Honest Lifecycle Tracking (Milestone 2B)**:
  - States distinguish static analysis (`analyzed`), artifact generation (`built`), and execution evidence (`runtime_verified`, `failed`).
  - A mounted canvas or successful build is never reported as runtime verification.
  - Static compatibility predictions remain separate from browser execution results.
- **Evidence-Based Browser Verification**:
  - Headless Chromium plus Pillow checks rendered canvas regions for color diversity, luminance variance, and game-specific visuals.
  - CarTraffic character selection, Flappy PLAY navigation, and PaddleGame level selection are exercised as real UI interactions.
  - Console diagnostics, screenshots, verification records, and demo lifecycle updates are retained as evidence.
  - PongGame's known audio failure is preserved as a `failed` verification, not hidden as a pass.
- **Hosted CI and Contributor Guardrails**:
  - GitHub-hosted runners only, minimal `contents: read` permissions, and pinned `project-2024` fixture commits.
  - Missing browser dependencies, fixtures, or network access fail in CI instead of skipping silently.

---

## Quick Start

### Installation

```bash
git clone https://github.com/AsistenProvikom/java-converter.git
cd java-converter

# Optional: install CLI in editable mode
pip install -e .
```

### Usage

#### 1. Analyze a single JAR archive
```bash
python3 -m provikom_converter analyze /path/to/game.jar
```
Or with installed CLI:
```bash
provikom-converter analyze /path/to/game.jar
```

To output raw JSON or save to file:
```bash
provikom-converter analyze /path/to/game.jar --json -o report.json
```

#### 2. Batch analyze a directory or game catalog
```bash
provikom-converter batch /path/to/games/ -o ./reports
```

#### 3. Build a playable web artifact
```bash
python3 -m provikom_converter build /path/to/game.jar \
  --backend cheerpj \
  --output ./demo/game
```

Use `--force` to replace an existing non-empty output directory, and `--title` to override the detected game title. Forced rebuilds are transactional: the previous artifact is replaced only after the new build succeeds.

The output is a self-contained static player directory:

```text
game/
├── index.html
├── style.css
├── app.js
├── manifest.json
├── Game.jar
├── verification.json  # optional runtime evidence
└── lib/               # staged Class-Path dependencies, when present
```

#### 4. Serve the artifact locally
```bash
python3 -m provikom_converter serve ./demo/game --port 8080
```

The built-in server supports HTTP Range Requests, which CheerpJ uses to stream JAR data.

#### 5. View JSON Schema specifications
```bash
python3 -m provikom_converter schema
```

Schema files:
- `schema/compatibility-report.schema.json` (analysis reports)
- `schema/artifact-manifest.schema.json` (generated artifacts; schema `1.1` adds lifecycle)

---

## Lifecycle and Verification Semantics

| State | Meaning |
|---|---|
| `analyzed` | Static analysis completed; no artifact exists. |
| `candidate` | Static analysis predicts buildability; no artifact yet. |
| `built` | Artifact generated successfully. This is **not** runtime verification. |
| `runtime_verified` | Browser checks confirmed rendered UI and expected interactions. |
| `failed` | Browser execution or verification failed. |
| `unsupported` | Selected backend cannot target the archive. |

Verification evidence lives in `verification.json` next to the artifact and in
`docs/verification/`. The manifest lifecycle is updated only from browser
evidence; the static `compatibility` block is never rewritten to imply runtime
success. See [docs/REPORT_SCHEMA.md](docs/REPORT_SCHEMA.md) for field details.

---

## Audit of `project-2024` Games

Batch analysis of all seven games in `AsistenProvikom/project-2024` yielded the following compatibility matrix:

| Game | File Size | Major Version | Swing/AWT | Audio API | CheerpJ 5.0 | TeaVM | SwingJS | Feasibility |
|---|---|---|---|---|---|---|---|---|
| `CarTraffic.jar` | 443 KB | Java 22 (v66) | Yes | None | **Supported** | Unsupported | Requires Source | Ready |
| `FrogieCrossTheRoad.jar` | 15.8 MB | Java 22 (v66) | Yes | `javax.sound.sampled` | **Supported (w/ workaround)** | Unsupported | Requires Source | Workaround (Audio) |
| `Minesweeper.jar` | 4.3 MB | Java 22 (v66) | Yes | `javax.sound.sampled` | **Supported (w/ workaround)** | Unsupported | Requires Source | Workaround (Audio) |
| `PaddleGame.jar` | 8.95 MB | Java 8 (v52) | Yes | `javax.sound.sampled` | **Supported (w/ workaround)** | Unsupported | Requires Source | Workaround (AbsoluteLayout & Audio) |
| `PongGame.jar` | 46.5 KB | Java 21 (v65) | Yes | `javax.sound.sampled` | **Supported (w/ workaround)** | Unsupported | Requires Source | Workaround (Audio) |
| `Snake Game FinPro.jar` | 30.1 KB | Java 22 (v66) | Yes | None | **Supported** | Unsupported | Requires Source | Ready |
| `flappy.jar` | 81.5 KB | Java 22 (v66) | Yes | None | **Supported** | Unsupported | Requires Source | Ready |

Full audit details: [docs/GAMES_COMPATIBILITY_AUDIT.md](docs/GAMES_COMPATIBILITY_AUDIT.md).

### Playable Demos

Pre-built bundles are committed under `demo/`. Lifecycle values reflect the latest automated browser evidence:

| Demo | Runtime | Lifecycle | Verification |
|---|---|---|---|
| `demo/car-traffic` | Java 25 experimental | `runtime_verified` | Menu rendered; character selection and NEXT navigation changed the UI. |
| `demo/flappy` | Java 25 experimental | `runtime_verified` | Menu rendered; PLAY opened gameplay. |
| `demo/paddle-game` | Java 8 | `runtime_verified` | Level select rendered; Easy mode started the game UI. `AbsoluteLayout.jar` staged automatically. |
| `demo/pong-game` | Java 21 | `failed` | Known audio limitation; error overlay verified and artifact retained for debugging. |

Evidence records:
- [CarTraffic](docs/verification/cartraffic.json)
- [Flappy](docs/verification/flappy.json)
- [PaddleGame](docs/verification/paddle-game.json)
- [PongGame](docs/verification/pong-game.json)

---

## Runtime and Licensing Notes

- **CheerpJ is proprietary.** CheerpJ 5.0 is a commercial runtime from Leaning Technologies. This repository does not relicense CheerpJ, its CDN assets, or its runtime. Review the vendor's licensing terms before production or commercial deployment. Offline/enterprise deployments require a vendor-supported package.
- **Java 22 games use an experimental runtime.** Java 22 bytecode maps to the experimental Java 25 preview candidate. Treat those demos as experimental, not production guarantees.
- **Demo game archives are third-party assets.** The MIT license covers the converter source and documentation, not the game JARs and screenshots under `demo/` and `docs/screenshots/`. These assets originate from `AsistenProvikom/project-2024`; no upstream LICENSE or NOTICE file was found during the Milestone 2B audit. Do not redistribute them without permission from the rights holders. For a fully publishable release, replace them with clearly licensed fixtures or remove them.
- **PongGame audio is a known limitation.** Browser `Clip` support rejects the game's 8-bit mono 44.1 kHz WAV. The player surfaces the Java exception; the artifact is intentionally kept available for debugging.
- **PaddleGame audio produces a non-fatal diagnostic.** `java.io.IOException: mark/reset not supported` is expected and does not prevent rendering or interaction.

---

## Security Model

- Untrusted game bytecode is never executed on the host or CI runner during analysis.
- JARs are copied unchanged into generated artifacts.
- Archive traversal, zip bombs, excessive entry counts, and abnormal compression ratios remain guarded.
- Forced output replacement validates source/output relationships and existing symlinks before deleting anything.
- Browser verification executes game code only inside headless Chromium on ephemeral GitHub-hosted runners.
- CI uses `contents: read`, disables persisted checkout credentials, and checks out a pinned `project-2024` commit for fixtures.
- Do not run untrusted pull requests on privileged self-hosted runners with internal network access.
- The local preview server is a development convenience; use a production static host with Range Request support for real deployments.

---

## Project Structure

```text
provikom-converter/
├── provikom_converter/
│   ├── analyzer/               # Safe archive reader, bytecode parser, heuristics
│   │   ├── archive.py
│   │   ├── bytecode.py
│   │   ├── compatibility.py
│   │   └── rules.py
│   ├── adapters/               # Backend adapter specifications
│   │   ├── base.py
│   │   ├── cheerpj.py
│   │   ├── swingjs.py
│   │   └── teavm.py
│   ├── orchestration/          # End-to-end analysis pipeline
│   │   └── pipeline.py
│   ├── artifacts/              # Report builder & serializer
│   │   └── report.py
│   ├── build_safety.py         # Validated, transactional artifact publishing
│   ├── lifecycle.py            # Lifecycle states and verification evidence
│   ├── server.py               # Range-Request HTTP server for artifacts
│   └── cli.py                  # CLI commands (analyze, build, serve, batch, schema)
├── .github/workflows/ci.yml    # Hosted CI with pinned fixtures and browser job
├── demo/                       # Generated playable web artifacts
├── docs/
│   ├── ARCHITECTURE.md         # Full architecture and threat model
│   ├── REPORT_SCHEMA.md        # JSON schema documentation
│   ├── GAMES_COMPATIBILITY_AUDIT.md
│   ├── MILESTONE_2_PLAN.md     # Web artifact generation roadmap
│   ├── MILESTONE_2A_REPORT.md  # CheerpJ builder results
│   ├── MILESTONE_2B_REPORT.md  # Hardening, CI, and verification evidence
│   ├── verification/           # Runtime verification records
│   └── screenshots/            # Browser verification evidence
├── schema/
│   ├── compatibility-report.schema.json
│   └── artifact-manifest.schema.json
├── tests/                      # Unit, integration, CLI, HTTP, and browser tests
├── reports/                    # Batch JSON and Markdown reports for 7 games
├── pyproject.toml
└── README.md
```

---

## Running Automated Tests

Run the core suite with Python's standard library `unittest`:

```bash
PROVIKOM_SKIP_BROWSER=1 python3 -m unittest discover -s tests -v
```

Core analysis, artifact, CLI, HTTP, schema, lifecycle, and build-safety tests have no third-party dependencies.

For strict local/CI-like fixture handling:

```bash
PROVIKOM_GAMES_DIR=/path/to/project-2024/games \
PROVIKOM_REQUIRE_FIXTURES=1 \
PROVIKOM_SKIP_BROWSER=1 \
python3 -m unittest discover -s tests -v
```

Browser verification requires Playwright, Chromium, Pillow, network access to the CheerpJ CDN, and the `project-2024` game JARs:

```bash
pip install -e ".[browser]"
python3 -m playwright install chromium

PROVIKOM_GAMES_DIR=/path/to/project-2024/games \
PROVIKOM_REQUIRE_FIXTURES=1 \
PROVIKOM_REQUIRE_BROWSER=1 \
python3 -m unittest discover -s tests -v
```

Expected results:
- Core suite without browser execution: **87 tests**, with the four browser classes skipped.
- Full suite with Playwright and fixtures: **93 tests**, 0 failures, 0 skips.

`PROVIKOM_REQUIRE_FIXTURES=1` and `PROVIKOM_REQUIRE_BROWSER=1` make missing fixtures, browser dependencies, or CDN access fatal. CI uses these flags so verification cannot silently degrade.

---

## License

The converter source and documentation are released under the MIT License. See [LICENSE](LICENSE).

Third-party game archives, screenshots of those games, CheerpJ, and other external assets are **not** covered by this repository's MIT license. See the runtime and licensing notes above.
