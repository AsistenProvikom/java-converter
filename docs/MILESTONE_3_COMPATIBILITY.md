# Milestone 3 - Source-Backed Swing Compatibility Testing

Date: 2026-11-23
Backend: SwingJS / Java2Script `5.0.1-v7`
Toolchain: JDK `17.0.21.1+2`, Eclipse `4.31.0` (2024-03 R),
Java2Script commit `4091b289014b99099481c37f7c151aeb24c713cd`

## Scope

Milestone 3 validates the source adapter against two independent Java 8 Swing
projects. It does **not** establish compatibility for the seven original
project-2024 games because their Java sources are unavailable.

No project-2024 game source was decompiled, reconstructed, or presented as an
original source port.

## Fixture Results

| Fixture | Main class | Source files | Result | Evidence |
|---|---|---|---|---|
| `examples/swing-poc` | `poc.SwingPoc` | 1 | `runtime_verified` | `docs/verification/swingjs-adapter-poc.json` |
| `examples/swing-widgets` | `compat.WidgetDemo` | 1 | `runtime_verified` | `docs/verification/swingjs-widgets.json` |

Screenshots:

- `docs/screenshots/swingjs-adapter-poc.png`
- `docs/screenshots/swingjs-widgets.png`

Both artifacts were built with `provikom build-project --backend swingjs`,
verified with `provikom verify-swingjs`, passed ownership validation, and
recorded source/generated-JavaScript hashes. The generated-JavaScript hashes
below are from the post-normalization builds. Two clean builds of each fixture
produced identical generated JavaScript bytes.

### Fixture 1: `SwingPoc`

Purpose: animation, keyboard handling, pause, reset, and application state.

Exercised APIs:

- `JFrame`, `JPanel`, `SwingUtilities.invokeLater`
- `Swing Timer`, `ActionListener`, `KeyStroke`/`AbstractAction`
- `Graphics2D`, `RenderingHints`, `Font`, `Color`
- `System.out` state reporting through the SwingJS output pane

Verified behavior:

- canvas mounted at 720x540;
- non-blank Graphics2D rendering;
- generated application JavaScript loaded with HTTP 200;
- timer tick advancement;
- left/right and up/down direction changes;
- Space pause and stable paused ticks;
- `R` reset to the initial state.

Source hash: `68f7a2ea7109845ecdca27278ef7864583e2e85178427bdc2ce408f417b93caa`

Generated JavaScript hash:
`8c423e12c13162d8907c52dcac7c77e1ff0a80e493f3f4b53aa1133937b02fa0`

### Fixture 2: `WidgetDemo`

Purpose: a second project using different Swing composition and mouse input,
without sharing the POC's code or interaction model.

Exercised APIs:

- `JFrame`, `JPanel`, `BorderLayout`
- `JButton`, `JLabel`, `ActionListener`
- `MouseAdapter`/`MouseEvent`
- `Swing Timer`, `Graphics2D`, `Font`, `Color`, `RenderingHints`
- `String.format` and application state reporting

Verified behavior:

- canvas mounted at 800x600;
- non-blank chart/circle rendering;
- generated application JavaScript loaded with HTTP 200;
- timer tick advancement;
- mouse press on the canvas increased the application click counter;
- `JButton` and `JLabel` rendered in the Swing layout.

Not independently asserted:

- JButton activation via a precise canvas click;
- focus traversal or keyboard operation of Swing controls;
- text input, clipboard, file chooser, or native dialogs.

Source hash: `3d2d7143000591440f73492aa5916710cbd6e9793dc905ee8fef1cef92be4aea`

Generated JavaScript hash:
`c17e964473a8b586cfa9ee2d585e3b7d81fcbba84139fa1cbf6de65b3ddbeae8`

## Compatibility Findings

Supported by these fixtures:

- Java 8 source compilation with `javac --release 8`;
- one discoverable source entry point;
- basic Swing containers and layout;
- Swing Timer-driven animation;
- Graphics2D primitives and antialiasing;
- key bindings and mouse events;
- `System.out` diagnostics;
- JButton and JLabel rendering.

Not yet proven:

- external JAR dependencies or resources (images, audio) from a source project;
- `JFileChooser`, `JTable`, `JTree`, `JTextArea` editing, or complex look and
  feel;
- audio playback;
- networking or persistent filesystem access;
- native look and feel, multiple windows, or applet-specific APIs;
- large projects, reflection, or third-party libraries;
- Java 9+ source.

## Required Source Changes

For these fixtures: none beyond standard Java source layout and a main class.

For a future real project:

1. Provide original Java 8-compatible source under `src/`.
2. Select one main class with `--main-class` if several exist.
3. Remove JavaFX/SWT code or isolate it behind an unsupported path.
4. Vendor required library **source** into the project; external binary JARs are
   not transpiled by this adapter.
5. Replace unsupported APIs or document them as limitations.
6. Add application-specific state output and verification only when it reflects
   the real application behavior.

## Original project-2024 Games

Only JARs are available. The following cannot be claimed as source-compatible
without original source or explicit permission to use reconstructed source:

- `CarTraffic.jar`
- `FrogieCrossTheRoad.jar`
- `Minesweeper.jar`
- `PaddleGame.jar`
- `PongGame.jar`
- `Snake Game FinPro.jar`
- `flappy.jar`

CheerpJ remains the verified path for these JAR-only inputs. See
`docs/MVP_BLOCKERS.md` and `docs/GAMES_COMPATIBILITY_AUDIT.md`.

## Reproduction

```bash
python3 tools/swingjs/setup_toolchain.py

python3 -m provikom_converter build-project examples/swing-poc \
  --backend swingjs -o build/swingjs-adapter-poc --force
python3 -m provikom_converter verify-swingjs build/swingjs-adapter-poc \
  --evidence build/swingjs-adapter-poc/verification.json \
  --screenshot build/swingjs-adapter-poc/verification.png

python3 -m provikom_converter build-project examples/swing-widgets \
  --backend swingjs -o build/swingjs-widgets --force
python3 -m provikom_converter verify-swingjs build/swingjs-widgets \
  --evidence build/swingjs-widgets/verification.json \
  --screenshot build/swingjs-widgets/verification.png
```

Generated runtime bundles remain local ignored artifacts and are not published
pending licensing review.
