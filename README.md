# Provikom Converter

[![Test Suite](https://img.shields.io/badge/tests-70%20passed-brightgreen.svg)]()
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()

**Provikom Converter** is an open-source Java game-to-web publishing tool. It analyzes Java game archives (compiled JARs, NetBeans projects) to assess browser compatibility across candidate runtimes and compilers (**CheerpJ**, **TeaVM**, **SwingJS**), and can generate playable CheerpJ 5.0 web artifacts without executing untrusted game code on the host.

---

## Key Capabilities (Milestones 1 and 2A)

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
- **CheerpJ 5.0 Playable Artifact Builder (Milestone 2A)**:
  - One-command generation of a static HTML/CSS/JS game player from an unmodified JAR.
  - Automatic runtime selection: Java 8, Java 21 LTS, or the experimental Java 25 preview target for Java 22 bytecode.
  - Automatic staging and classpath registration of manifest `Class-Path` dependencies (for example `lib/AbsoluteLayout.jar`).
  - Official CheerpJ APIs (`cheerpjInit`, `cheerpjCreateDisplay`, `cheerpjRunMain`) with `/app/` asset mounting.
  - In-page loading, compatibility, and Java exception diagnostics.
  - Range-Request-capable local HTTP server for reliable JAR streaming.
  - Headless Chromium verification suite with committed screenshots.

---

## Quick Start

### Installation

```bash
git clone https://github.com/AsistenProvikom/provikom-converter.git
cd provikom-converter

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

Use `--force` to replace an existing non-empty output directory, and `--title` to override the detected game title.

The output is a self-contained static player directory:

```text
game/
├── index.html
├── style.css
├── app.js
├── manifest.json
├── Game.jar
└── lib/           # staged Class-Path dependencies, when present
```

#### 4. Serve the artifact locally
```bash
python3 -m provikom_converter serve ./demo/game --port 8080
```

The built-in server supports HTTP Range Requests, which CheerpJ uses to stream JAR data.

#### 5. View JSON Schema specification
```bash
python3 -m provikom_converter schema
```

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

Pre-built bundles are committed under `demo/`:

| Demo | Runtime | Notes |
|---|---|---|
| `demo/car-traffic` | Java 25 experimental | Menu, character selection, and theme navigation verified |
| `demo/flappy` | Java 25 experimental | Menu and gameplay verified |
| `demo/paddle-game` | Java 8 | `AbsoluteLayout.jar` staged automatically |
| `demo/pong-game` | Java 21 | Known audio limitation; error overlay verified |

Milestone 2A report and browser evidence: [docs/MILESTONE_2A_REPORT.md](docs/MILESTONE_2A_REPORT.md).

---

## Project Structure

```
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
│   ├── server.py               # Range-Request HTTP server for artifacts
│   └── cli.py                  # CLI commands (analyze, build, serve, batch, schema)
├── demo/                       # Generated playable web artifacts
├── docs/
│   ├── ARCHITECTURE.md         # Full architecture and threat model
│   ├── REPORT_SCHEMA.md        # JSON schema documentation
│   ├── GAMES_COMPATIBILITY_AUDIT.md
│   ├── MILESTONE_2_PLAN.md     # Web artifact generation roadmap
│   ├── MILESTONE_2A_REPORT.md  # CheerpJ builder results and screenshots
│   └── screenshots/            # Browser verification evidence
├── schema/
│   └── compatibility-report.schema.json
├── tests/                      # Unit, integration, CLI, and browser tests
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

Core analysis, artifact, CLI, and HTTP tests have no third-party dependencies.

Browser verification requires Playwright, Chromium, network access to the CheerpJ CDN, and the local `project-2024` game JARs:

```bash
pip install playwright
python3 -m playwright install chromium
python3 -m unittest discover -s tests -v
```

The full suite currently reports **70 tests passed, 0 failures** in about 100 seconds with the browser classes enabled. When `PROVIKOM_SKIP_BROWSER=1` is set, 64 tests run and the four browser test classes are reported as skipped.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
