"""Compatibility evaluation engine for Provikom Converter.

Evaluates detected features and archive properties against CheerpJ, TeaVM,
and SwingJS backends with rigorous distinction between verified facts and assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from provikom_converter.analyzer.archive import ArchiveInventory
from provikom_converter.analyzer.bytecode import java_version_from_major
from provikom_converter.analyzer.rules import AnalysisFeatures


class CompatibilityStatus(str, Enum):
    SUPPORTED = "supported"
    SUPPORTED_WITH_WORKAROUNDS = "supported_with_workarounds"
    UNSUPPORTED = "unsupported"
    REQUIRES_SOURCE = "requires_source"
    UNKNOWN = "unknown"


@dataclass
class BackendEvaluation:
    backend_id: str
    backend_name: str
    is_open_source: bool
    status: CompatibilityStatus
    confidence_score: float  # 0.0 to 1.0
    summary: str
    verified_capabilities: List[str] = field(default_factory=list)
    assumptions_and_risks: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    workarounds_needed: List[str] = field(default_factory=list)
    remediation_steps: List[str] = field(default_factory=list)


class CompatibilityEvaluator:
    """Evaluates archive and bytecode features against browser runtime backends."""

    def __init__(
        self,
        inventory: ArchiveInventory,
        features: AnalysisFeatures,
        class_major_versions: List[int],
    ):
        self.inventory = inventory
        self.features = features
        self.major_versions = class_major_versions
        self.max_major = max(class_major_versions) if class_major_versions else 0
        self.min_major = min(class_major_versions) if class_major_versions else 0

    def evaluate_cheerpj(self) -> BackendEvaluation:
        verified: List[str] = []
        risks: List[str] = []
        blockers: List[str] = []
        workarounds: List[str] = []
        remediation: List[str] = []

        verified.append("Accepts compiled binary JAR input directly without source code.")
        
        # Check Java version
        max_ver_str = java_version_from_major(self.max_major)
        if self.max_major <= 66:  # Up to Java 22 / CheerpJ 5.0
            verified.append(f"Bytecode major version {self.max_major} ({max_ver_str}) is supported by CheerpJ 5.0 runtime.")
        else:
            risks.append(f"Class version {self.max_major} exceeds tested CheerpJ 5.0 baseline.")

        # Check GUI framework
        has_swing = any(f.name == "Java Swing" for f in self.features.gui_frameworks)
        has_awt = any(f.name == "Java AWT" for f in self.features.gui_frameworks)
        has_javafx = any(f.name == "JavaFX" for f in self.features.gui_frameworks)

        if has_swing or has_awt:
            verified.append("CheerpJ provides client-side OpenJDK AWT/Swing canvas rendering.")
        if has_javafx:
            risks.append("JavaFX in CheerpJ requires OpenJFX runtime jars on the virtual classpath.")

        # Check native code
        if self.inventory.native_libraries or any(f.category == "native" for f in self.features.native_features):
            blockers.append("JNI/native binary libraries cannot execute inside WebAssembly sandbox.")
            remediation.append("Remove native C/C++ libraries and replace with pure Java equivalents.")

        # Check networking
        if any(f.name.startswith("Raw TCP") for f in self.features.network_apis):
            blockers.append("Direct TCP/UDP sockets cannot connect directly from the browser.")
            remediation.append("Provide a WebSocket-to-TCP proxy server or CheerpJ network tunnel.")

        # Check external dependencies / NetBeans AbsoluteLayout
        has_nb = any(f.name == "NetBeans AbsoluteLayout" for f in self.features.external_libraries)
        if has_nb:
            workarounds.append("Requires external NetBeans 'lib/AbsoluteLayout.jar' mounted into CheerpOS filesystem.")
            remediation.append("Bundle 'AbsoluteLayout.jar' and load it before launching the main JAR.")

        # Audio risks
        has_audio = bool(self.features.audio_apis)
        if has_audio:
            risks.append("Browser audio autoplay policy requires user interaction before audio starts.")
            workarounds.append("Ensure game startup waits for user click or initialize Web Audio context on user gesture.")

        # Direct file IO
        has_file_io = bool(self.features.io_apis)
        if has_file_io:
            risks.append("Direct disk file operations access in-memory CheerpOS virtual filesystem (data resets on refresh unless indexedDB persistence is configured).")

        # Determine status
        if blockers:
            status = CompatibilityStatus.UNSUPPORTED
            confidence = 0.95
            summary = "CheerpJ cannot run this game due to unresolvable browser sandbox constraints (native code or direct sockets)."
        elif workarounds:
            status = CompatibilityStatus.SUPPORTED_WITH_WORKAROUNDS
            confidence = 0.90
            summary = "CheerpJ can run this game provided external dependencies or virtual filesystem assets are staged."
        else:
            status = CompatibilityStatus.SUPPORTED
            confidence = 0.92
            summary = "CheerpJ supports this JAR directly with high expected compatibility."

        return BackendEvaluation(
            backend_id="cheerpj",
            backend_name="CheerpJ 5.0 (Leaning Technologies)",
            is_open_source=False,
            status=status,
            confidence_score=confidence,
            summary=summary,
            verified_capabilities=verified,
            assumptions_and_risks=risks,
            blockers=blockers,
            workarounds_needed=workarounds,
            remediation_steps=remediation,
        )

    def evaluate_teavm(self) -> BackendEvaluation:
        verified: List[str] = []
        risks: List[str] = []
        blockers: List[str] = []
        workarounds: List[str] = []
        remediation: List[str] = []

        verified.append("Open-source ahead-of-time (AOT) compiler targeting JavaScript and WebAssembly.")

        # Check GUI framework - TeaVM does NOT support Swing or AWT!
        has_swing = any(f.name == "Java Swing" for f in self.features.gui_frameworks)
        has_awt = any(f.name == "Java AWT" for f in self.features.gui_frameworks)

        if has_swing or has_awt:
            blockers.append("TeaVM does not provide an implementation of 'javax.swing.*' or 'java.awt.*'.")
            remediation.append("Port the user interface to TeaVM Canvas / HTML5 DOM or use an AWT-to-Canvas compatibility layer.")

        has_audio = bool(self.features.audio_apis)
        if has_audio:
            blockers.append("TeaVM core does not implement 'javax.sound.sampled.*' (AudioSystem/Clip).")
            remediation.append("Implement custom TeaVM JavaScript overlays using Web Audio API.")

        # Threading in TeaVM
        has_threading = any(f.name.startswith("Standard Threading") for f in self.features.threading_apis)
        if has_threading:
            risks.append("Thread.sleep() and blocking loops require TeaVM asynchronous transformation mode or event-loop refactoring.")

        # Reflection
        has_reflection = bool(self.features.reflection_apis)
        if has_reflection:
            risks.append("Reflection requires explicit class preservation descriptors in TeaVM configuration.")

        # Java version
        if self.max_major > 65:
            risks.append(f"Bytecode version {self.max_major} (Java 22) may require TeaVM bytecode parser updates or target release downgrade.")

        if blockers:
            status = CompatibilityStatus.UNSUPPORTED
            confidence = 0.98
            summary = "TeaVM cannot compile this desktop game directly because Swing and AWT are missing from its class library."
        else:
            status = CompatibilityStatus.SUPPORTED
            confidence = 0.70
            summary = "Code logic is potentially transpilable via TeaVM."

        return BackendEvaluation(
            backend_id="teavm",
            backend_name="TeaVM (AOT Bytecode to JS/Wasm)",
            is_open_source=True,
            status=status,
            confidence_score=confidence,
            summary=summary,
            verified_capabilities=verified,
            assumptions_and_risks=risks,
            blockers=blockers,
            workarounds_needed=workarounds,
            remediation_steps=remediation,
        )

    def evaluate_swingjs(self) -> BackendEvaluation:
        verified: List[str] = []
        risks: List[str] = []
        blockers: List[str] = []
        workarounds: List[str] = []
        remediation: List[str] = []

        verified.append("Open-source Java-to-JavaScript system with comprehensive Swing and AWT emulation.")

        # Input type requirement: SwingJS works at the Java SOURCE level, not compiled binary JARs!
        blockers.append("SwingJS requires Java source code (.java) for AST transpilation; it cannot compile standalone binary JARs directly.")
        remediation.append("Provide original Java source code or decompile the JAR classes using CFR / Fernflower.")

        # Java version compatibility
        if self.max_major > 52:
            ver_str = java_version_from_major(self.max_major)
            blockers.append(f"Class bytecode is {ver_str} (major {self.max_major}). SwingJS's transpiler is designed for Java 8 (with experimental Java 11 support).")
            remediation.append("Downgrade or retarget decompiled Java source to Java 8/11 language level.")

        # NetBeans AbsoluteLayout
        has_nb = any(f.name == "NetBeans AbsoluteLayout" for f in self.features.external_libraries)
        if has_nb:
            workarounds.append("NetBeans AbsoluteLayout source must be included in the SwingJS build classpath.")

        status = CompatibilityStatus.REQUIRES_SOURCE
        confidence = 0.95
        summary = "SwingJS provides high Swing UI compatibility, but requires original or decompiled Java source and Java 8/11 syntax."

        return BackendEvaluation(
            backend_id="swingjs",
            backend_name="SwingJS / Java2Script",
            is_open_source=True,
            status=status,
            confidence_score=confidence,
            summary=summary,
            verified_capabilities=verified,
            assumptions_and_risks=risks,
            blockers=blockers,
            workarounds_needed=workarounds,
            remediation_steps=remediation,
        )

    def evaluate_all(self) -> Dict[str, BackendEvaluation]:
        return {
            "cheerpj": self.evaluate_cheerpj(),
            "teavm": self.evaluate_teavm(),
            "swingjs": self.evaluate_swingjs(),
        }
