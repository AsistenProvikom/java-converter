# Provikom Converter

[![Test Suite](https://img.shields.io/badge/tests-26%20passed-brightgreen.svg)]()
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()

**Provikom Converter** is an open-source Java game-to-web publishing tool. It analyzes Java game archives (compiled JARs, NetBeans projects) to assess browser compatibility across candidate runtimes and compilers (**CheerpJ**, **TeaVM**, **SwingJS**), producing reproducible compatibility reports without executing untrusted game code.

---

## Key Capabilities (Milestone 1)

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

#### 3. View JSON Schema specification
```bash
provikom-converter schema
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

Full audit details: [docs/GAMES_COMPATIBILITY_AUDIT.md](file:///home/hafidz/project/java-converter/docs/GAMES_COMPATIBILITY_AUDIT.md).

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
│   └── cli.py                  # CLI commands (analyze, batch, schema)
├── docs/
│   ├── ARCHITECTURE.md         # Full architecture and threat model
│   ├── REPORT_SCHEMA.md        # JSON schema documentation
│   ├── GAMES_COMPATIBILITY_AUDIT.md
│   └── MILESTONE_2_PLAN.md     # Web artifact generation roadmap
├── schema/
│   └── compatibility-report.schema.json
├── tests/                      # Automated unit and integration tests
├── reports/                    # Batch JSON and Markdown reports for 7 games
├── pyproject.toml
└── README.md
```

---

## Running Automated Tests

Run the full test suite with Python's standard library `unittest`:

```bash
python3 -m unittest discover -s tests -v
```

All 26 tests run in under 0.1s with zero external dependencies.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
