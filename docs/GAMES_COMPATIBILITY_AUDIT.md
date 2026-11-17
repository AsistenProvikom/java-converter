# Project 2024 - Compatibility Audit Report

Detailed audit covering the seven Java game archives from the `AsistenProvikom/project-2024` showcase repository, analyzed using `provikom-converter`.

---

## 1. Inventory Summary

| # | File Name | Size (bytes) | Class Files | Resource Files | Max Bytecode Version | Manifest Main-Class | Manifest Class-Path |
|---|---|---|---|---|---|---|---|
| 1 | `CarTraffic.jar` | 453,769 | 18 | 37 | Java 22 (v66) | `main.Main` | *(none)* |
| 2 | `FrogieCrossTheRoad.jar` | 16,561,338 | 15 | 46 | Java 22 (v66) | `main.Main` | *(none)* |
| 3 | `Minesweeper.jar` | 4,511,044 | 18 | 6 | Java 22 (v66) | `tugasakhir1.Start` | *(none)* |
| 4 | `PaddleGame.jar` | 9,387,639 | 17 | 18 | Java 8 (v52) | `keyboarddemo.LevelFrame` | `lib/AbsoluteLayout.jar` |
| 5 | `PongGame.jar` | 47,670 | 28 | 6 | Java 21 (v65) | `ucupandriska.ponggame.Main` | *(none)* |
| 6 | `Snake Game FinPro.jar` | 30,877 | 11 | 0 | Java 22 (v66) | `SnakeMain` | *(none)* |
| 7 | `flappy.jar` | 83,462 | 6 | 5 | Java 22 (v66) | `MainMenu` | *(none)* |

---

## 2. In-Depth Audit Findings by Game

### 1. `CarTraffic.jar`
- **SHA-256**: `f2ebef96d66e7ea81aa128e07817eb4185799bb3c87e6fa16b04b901cb188047`
- **Compiler**: JDK 22 (`major_version = 66`)
- **UI Frameworks**: Swing (`JFrame`, `JPanel`, `JButton`, `Timer`), AWT (`Graphics`, `Color`, `Rectangle`)
- **Audit Findings**:
  - Contains an embedded zip entry named `Final Project_Zidane Sindhu.jar` (8,838 bytes).
  - Contains 36 bundled PNG sprites.
  - No audio APIs or direct disk file writes detected.
- **Backend Suitability**:
  - **CheerpJ 5.0**: **Supported (Ready)**. CheerpJ 5 supports Java 22 bytecode and runs Swing smoothly on canvas.
  - **TeaVM**: **Unsupported**. Blocked by `javax.swing.JFrame` and `java.awt.Graphics`.
  - **SwingJS**: **Requires Source**. Would require decompilation to Java source.

### 2. `FrogieCrossTheRoad.jar`
- **SHA-256**: `5e02ba94a5047b4d18ec8239062eb147321eb1fb76595ae1cbdf7497d39ef8fe`
- **Compiler**: JDK 22 (`major_version = 66`)
- **UI Frameworks**: Swing (`JFrame`, `JPanel`), AWT (`MouseListener`, `BufferedImage`)
- **Audio API**: `javax.sound.sampled` (`Clip`, `AudioSystem`, `AudioInputStream`)
- **Audit Findings**:
  - Contains 4 `.wav` sound files and 1 TrueType font `font/font.ttf`.
  - Heaviest archive in the gallery (16.5 MB uncompressed).
- **Backend Suitability**:
  - **CheerpJ 5.0**: **Supported with Workarounds**. Runtime needs user interaction to activate browser Web Audio context.
  - **TeaVM**: **Unsupported**.
  - **SwingJS**: **Requires Source**.

### 3. `Minesweeper.jar`
- **SHA-256**: `d7e57c8cfa2bdf99395b0561ea9d10e05697669d031da7ef8bb2825bc5312015`
- **Compiler**: JDK 22 (`major_version = 66`)
- **UI Frameworks**: NetBeans Swing (`GroupLayout`, `JButton`, `JLabel`, `Timer`)
- **Audio API**: `javax.sound.sampled.AudioSystem`, `Clip`
- **Audit Findings**:
  - 5 `.gif` assets and 1 `.wav` sound file.
  - Standard NetBeans form design with heavy `GroupLayout` usage.
- **Backend Suitability**:
  - **CheerpJ 5.0**: **Supported with Workarounds** (audio autoplay policy).
  - **TeaVM**: **Unsupported**.
  - **SwingJS**: **Requires Source**.

### 4. `PaddleGame.jar`
- **SHA-256**: `41b423488d9aba93f184ce56281417a836996417e5ed85404b8174034973b8dd`
- **Compiler**: JDK 8 (`major_version = 52`)
- **UI Frameworks**: Swing (`JFrame`, `JPanel`, `TitledBorder`, `Timer`), AWT
- **Audio API**: `javax.sound.sampled` (10 `.wav` files)
- **External Dependency**: NetBeans `AbsoluteLayout` (`lib/AbsoluteLayout.jar`)
- **File I/O**: `java.io.FileInputStream` / `FileOutputStream`
- **Audit Findings**:
  - Only game compiled with Java 8 (`major = 52`).
  - `MANIFEST.MF` explicitly defines `Class-Path: lib/AbsoluteLayout.jar`.
  - In `project-2024`, `games/lib/AbsoluteLayout.jar` is provided in the repository and loaded via `cheerOSAddStringFile('/str/lib/AbsoluteLayout.jar', bytes)` in `script.js`.
- **Backend Suitability**:
  - **CheerpJ 5.0**: **Supported with Workarounds**. Requires mounting `lib/AbsoluteLayout.jar` into the CheerpOS virtual filesystem before launching.
  - **TeaVM**: **Unsupported**.
  - **SwingJS**: **Requires Source / High Potential Candidate**. Because the bytecode is already Java 8, decompiled source matches SwingJS syntax natively.

### 5. `PongGame.jar`
- **SHA-256**: `c53755c3c0ef0f772fe0d8f99762dfcf9c8691515bb5602492fdf16410427670`
- **Compiler**: JDK 21 LTS (`major_version = 65`)
- **UI Frameworks**: Swing (`JFrame`, `SwingUtilities`), AWT (`Graphics2D`, `AlphaComposite`, `Rectangle2D$Double`)
- **Audio API**: `javax.sound.sampled` (4 `.wav` files)
- **Backend Suitability**:
  - **CheerpJ 5.0**: **Supported with Workarounds** (audio autoplay).
  - **TeaVM**: **Unsupported**.
  - **SwingJS**: **Requires Source**.

### 6. `Snake Game FinPro.jar`
- **SHA-256**: `fcf03c7eaae1d7134cb623dd25b33be46df8f5f4b598ff7f81bf8350b284e31e`
- **Compiler**: JDK 22 (`major_version = 66`)
- **UI Frameworks**: Swing (`JFrame`, `JPanel`, `Timer`, `JOptionPane`), AWT (`GradientPaint`)
- **File I/O**: `java.io.File`, `FileInputStream`, `FileOutputStream` for high scores.
- **Backend Suitability**:
  - **CheerpJ 5.0**: **Supported (Ready)**. Virtual filesystem persists scores during session.
  - **TeaVM**: **Unsupported**.
  - **SwingJS**: **Requires Source**.

### 7. `flappy.jar`
- **SHA-256**: `c788986652405b12da6a6ec1544ee03f831b539c2d1b8c8bef6f4d3a0de4b0ea`
- **Compiler**: JDK 22 (`major_version = 66`)
- **UI Frameworks**: NetBeans Swing (`GroupLayout`, `JButton`, `JLabel`, `Timer`)
- **Audio API**: None
- **Backend Suitability**:
  - **CheerpJ 5.0**: **Supported (Ready)**.
  - **TeaVM**: **Unsupported**.
  - **SwingJS**: **Requires Source**.
