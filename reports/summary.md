# Project 2024 - Java Game Compatibility Audit

This document summarizes the automated compatibility analysis of all seven Java games bundled in `AsistenProvikom/project-2024`, performed by `provikom-converter` (v0.1.0).

---

## Executive Summary Matrix

| Game Archive | Size | Entry Point (`Main-Class`) | Class Version | GUI Framework | Audio API | Dependencies / Notes | CheerpJ 5.0 | TeaVM | SwingJS | Feasibility |
|---|---|---|---|---|---|---|---|---|---|---|
| **`CarTraffic.jar`** | 443 KB | `main.Main` | Java 22 (v66) | Swing, AWT | None | Embedded JAR detected (`Final Project_Zidane Sindhu.jar`) | **Supported** | Unsupported | Requires Source | Ready |
| **`FrogieCrossTheRoad.jar`** | 15.8 MB | `main.Main` | Java 22 (v66) | Swing, AWT | `javax.sound.sampled` | 4 WAV files, 1 TTF font, large uncompressed assets | **Supported (w/ workaround)** | Unsupported | Requires Source | Workaround Req. (Audio) |
| **`Minesweeper.jar`** | 4.3 MB | `tugasakhir1.Start` | Java 22 (v66) | Swing, AWT | `javax.sound.sampled` | 5 GIF assets, 1 WAV file | **Supported (w/ workaround)** | Unsupported | Requires Source | Workaround Req. (Audio) |
| **`PaddleGame.jar`** | 8.95 MB | `keyboarddemo.LevelFrame` | Java 8 (v52) | Swing, AWT | `javax.sound.sampled` | Manifest references `lib/AbsoluteLayout.jar`; 10 WAV files | **Supported (w/ workaround)** | Unsupported | Requires Source | Workaround Req. (NetBeans dep & Audio) |
| **`PongGame.jar`** | 46.5 KB | `ucupandriska.ponggame.Main` | Java 21 (v65) | Swing, AWT | `javax.sound.sampled` | 4 WAV files, 1 TTF font | **Supported (w/ workaround)** | Unsupported | Requires Source | Workaround Req. (Audio) |
| **`Snake Game FinPro.jar`** | 30.1 KB | `SnakeMain` | Java 22 (v66) | Swing, AWT | None | Self-contained, file I/O for score saving | **Supported** | Unsupported | Requires Source | Ready |
| **`flappy.jar`** | 81.5 KB | `MainMenu` | Java 22 (v66) | Swing, AWT | None | Self-contained Swing game with Timer loop | **Supported** | Unsupported | Requires Source | Ready |

---

## Detailed Game Breakdown

### 1. `CarTraffic.jar`
- **Bytecode Major Version**: 66 (Java 22)
- **GUI Framework**: Swing (`JFrame`, `JPanel`, `JButton`, `Timer`), AWT (`Graphics`, `Color`, `Rectangle`)
- **Audio API**: None detected
- **Notable Observations**: Contains an embedded inner JAR file `Final Project_Zidane Sindhu.jar` (8,838 bytes) containing duplicate class files from an earlier student build. Does not impact runtime if main classes are loaded from archive root.
- **CheerpJ Status**: **SUPPORTED**. Runs directly in CheerpJ 5.0 canvas display.
- **TeaVM Status**: **UNSUPPORTED**. Blocked by missing `javax.swing.*` and `java.awt.*`.
- **SwingJS Status**: **REQUIRES SOURCE**. Requires decompilation and Java 8/11 language downgrade.

### 2. `FrogieCrossTheRoad.jar`
- **Bytecode Major Version**: 66 (Java 22)
- **GUI Framework**: Swing (`JFrame`, `JPanel`), AWT (`MouseListener`, `BufferedImage`, `Dimension`)
- **Audio API**: `javax.sound.sampled.Clip`, `AudioSystem`, `AudioInputStream`
- **Notable Observations**: Includes 4 uncompressed `.wav` sound files and custom TrueType font `font/font.ttf`.
- **CheerpJ Status**: **SUPPORTED WITH WORKAROUNDS**. Browser audio autoplay policy requires user interaction before audio starts.
- **TeaVM Status**: **UNSUPPORTED**. Blocked by missing Swing, AWT, and `javax.sound.sampled`.
- **SwingJS Status**: **REQUIRES SOURCE**.

### 3. `Minesweeper.jar`
- **Bytecode Major Version**: 66 (Java 22)
- **GUI Framework**: NetBeans generated Swing GUI (`GroupLayout`, `JButton`, `JLabel`, `Timer`)
- **Audio API**: `javax.sound.sampled.AudioSystem`, `Clip`
- **Notable Observations**: Built with NetBeans GUI designer; uses `GroupLayout` extensively.
- **CheerpJ Status**: **SUPPORTED WITH WORKAROUNDS**. Audio initialization on user click.
- **TeaVM Status**: **UNSUPPORTED**. Blocked by missing Swing/AWT.
- **SwingJS Status**: **REQUIRES SOURCE**.

### 4. `PaddleGame.jar`
- **Bytecode Major Version**: 52 (Java 8)
- **GUI Framework**: Swing (`JFrame`, `JPanel`, `TitledBorder`, `Timer`), AWT
- **Audio API**: `javax.sound.sampled` (`Clip`, `LineListener`, `AudioSystem`)
- **Notable Observations**: 
  - Compiled for Java 8 (class version 52), unlike the other games which were compiled with Java 21/22.
  - Manifest specifies `Class-Path: lib/AbsoluteLayout.jar`.
  - Bytecode depends on `org.netbeans.lib.awtextra.AbsoluteLayout` and `AbsoluteConstraints`.
  - Uses `java.io.FileInputStream` / `FileOutputStream` for local score saving.
- **CheerpJ Status**: **SUPPORTED WITH WORKAROUNDS**. Requires staging `games/lib/AbsoluteLayout.jar` into the CheerpOS virtual filesystem path prior to execution.
- **TeaVM Status**: **UNSUPPORTED**.
- **SwingJS Status**: **REQUIRES SOURCE** (High viability candidate for SwingJS since the bytecode is already Java 8; decompiled code requires minimal modern Java syntax downgrading).

### 5. `PongGame.jar`
- **Bytecode Major Version**: 65 (Java 21 LTS)
- **GUI Framework**: Swing (`JFrame`, `SwingUtilities`), AWT (`Graphics2D`, `AlphaComposite`, `Rectangle2D$Double`)
- **Audio API**: `javax.sound.sampled` (`Clip`, `AudioSystem`)
- **Notable Observations**: Modern Java 21 bytecode; uses Java 2D double precision geometry for physics.
- **CheerpJ Status**: **SUPPORTED WITH WORKAROUNDS** (audio autoplay policy).
- **TeaVM Status**: **UNSUPPORTED**.
- **SwingJS Status**: **REQUIRES SOURCE**.

### 6. `Snake Game FinPro.jar`
- **Bytecode Major Version**: 66 (Java 22)
- **GUI Framework**: Swing (`JFrame`, `JPanel`, `Timer`, `JOptionPane`), AWT (`GradientPaint`, `RenderingHints`)
- **Audio API**: None
- **Notable Observations**: Uses `java.io.File` / streams for high score persistence; runs cleanly in CheerpOS memory virtual disk.
- **CheerpJ Status**: **SUPPORTED**.
- **TeaVM Status**: **UNSUPPORTED**.
- **SwingJS Status**: **REQUIRES SOURCE**.

### 7. `flappy.jar`
- **Bytecode Major Version**: 66 (Java 22)
- **GUI Framework**: NetBeans generated Swing GUI (`GroupLayout`, `JButton`, `JLabel`, `Timer`)
- **Audio API**: None
- **Notable Observations**: Simple, compact flappy bird clone.
- **CheerpJ Status**: **SUPPORTED**.
- **TeaVM Status**: **UNSUPPORTED**.
- **SwingJS Status**: **REQUIRES SOURCE**.
