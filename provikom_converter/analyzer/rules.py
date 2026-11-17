"""Feature detection and heuristic analysis rules for Provikom Converter.

Categorizes JVM API usage into structured capability groups for evaluating
browser runtime compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from provikom_converter.analyzer.bytecode import ParsedClassFile


@dataclass
class DetectedFeature:
    category: str
    name: str
    description: str
    severity: str  # 'info', 'warning', 'blocker'
    matched_symbols: List[str] = field(default_factory=list)


@dataclass
class AnalysisFeatures:
    gui_frameworks: List[DetectedFeature] = field(default_factory=list)
    audio_apis: List[DetectedFeature] = field(default_factory=list)
    threading_apis: List[DetectedFeature] = field(default_factory=list)
    io_apis: List[DetectedFeature] = field(default_factory=list)
    network_apis: List[DetectedFeature] = field(default_factory=list)
    reflection_apis: List[DetectedFeature] = field(default_factory=list)
    external_libraries: List[DetectedFeature] = field(default_factory=list)
    native_features: List[DetectedFeature] = field(default_factory=list)
    all_features: List[DetectedFeature] = field(default_factory=list)


class FeatureDetector:
    """Evaluates parsed classes and constant pools against known compatibility heuristics."""

    def __init__(self, parsed_classes: List[ParsedClassFile], manifest_classpath: List[str]):
        self.classes = parsed_classes
        self.manifest_classpath = manifest_classpath

    def detect(self) -> AnalysisFeatures:
        all_referenced_classes: Set[str] = set()
        all_referenced_packages: Set[str] = set()
        all_method_calls: Set[Tuple[str, str]] = set()
        has_native_methods = False

        for pc in self.classes:
            all_referenced_classes.update(pc.referenced_classes)
            all_referenced_packages.update(pc.referenced_packages)
            for mr in pc.method_refs:
                all_method_calls.add((mr.class_name, mr.method_name))
            if pc.has_native_methods:
                has_native_methods = True

        features = AnalysisFeatures()

        # 1. GUI Frameworks
        swing_symbols = [c for c in all_referenced_classes if c.startswith("javax/swing/")]
        if swing_symbols:
            feat = DetectedFeature(
                category="gui",
                name="Java Swing",
                description="Desktop Swing UI components detected.",
                severity="info",
                matched_symbols=sorted(swing_symbols)[:15],
            )
            features.gui_frameworks.append(feat)

        awt_symbols = [c for c in all_referenced_classes if c.startswith("java/awt/")]
        if awt_symbols:
            feat = DetectedFeature(
                category="gui",
                name="Java AWT",
                description="Abstract Window Toolkit (AWT) graphics and event handling detected.",
                severity="info",
                matched_symbols=sorted(awt_symbols)[:15],
            )
            features.gui_frameworks.append(feat)

        javafx_symbols = [c for c in all_referenced_classes if c.startswith("javafx/")]
        if javafx_symbols:
            feat = DetectedFeature(
                category="gui",
                name="JavaFX",
                description="JavaFX UI framework detected (requires OpenJFX runtime).",
                severity="warning",
                matched_symbols=sorted(javafx_symbols)[:15],
            )
            features.gui_frameworks.append(feat)

        swt_symbols = [c for c in all_referenced_classes if c.startswith("org/eclipse/swt/")]
        if swt_symbols:
            feat = DetectedFeature(
                category="gui",
                name="Eclipse SWT",
                description="Standard Widget Toolkit (SWT) native UI detected.",
                severity="blocker",
                matched_symbols=sorted(swt_symbols)[:15],
            )
            features.gui_frameworks.append(feat)

        # 2. Audio APIs
        sound_symbols = [c for c in all_referenced_classes if c.startswith("javax/sound/sampled/")]
        if sound_symbols:
            feat = DetectedFeature(
                category="audio",
                name="Java Sound Sampled (javax.sound.sampled)",
                description="Audio playback (Clip, AudioSystem, Line) detected.",
                severity="info",
                matched_symbols=sorted(sound_symbols)[:10],
            )
            features.audio_apis.append(feat)

        midi_symbols = [c for c in all_referenced_classes if c.startswith("javax/sound/midi/")]
        if midi_symbols:
            feat = DetectedFeature(
                category="audio",
                name="Java Sound MIDI (javax.sound.midi)",
                description="MIDI sound synthesizer detected.",
                severity="warning",
                matched_symbols=sorted(midi_symbols)[:10],
            )
            features.audio_apis.append(feat)

        # 3. Concurrency & Threading
        thread_symbols = [c for c in all_referenced_classes if c in ("java/lang/Thread", "java/lang/Runnable")]
        if thread_symbols:
            feat = DetectedFeature(
                category="threading",
                name="Standard Threading (java.lang.Thread / Runnable)",
                description="Multi-threading or runnable game loop detected.",
                severity="info",
                matched_symbols=sorted(thread_symbols),
            )
            features.threading_apis.append(feat)

        concurrent_symbols = [c for c in all_referenced_classes if c.startswith("java/util/concurrent/")]
        if concurrent_symbols:
            feat = DetectedFeature(
                category="threading",
                name="Java Concurrency Utilities (java.util.concurrent)",
                description="Thread pools, Futures, or atomic state primitives detected.",
                severity="info",
                matched_symbols=sorted(concurrent_symbols)[:10],
            )
            features.threading_apis.append(feat)

        # 4. File I/O & Storage
        io_symbols = [c for c in all_referenced_classes if c.startswith("java/io/File") or c.startswith("java/io/RandomAccessFile")]
        if io_symbols:
            feat = DetectedFeature(
                category="io",
                name="Direct File System I/O (java.io.File)",
                description="Direct disk file read/write detected. Requires virtual filesystem in browser.",
                severity="warning",
                matched_symbols=sorted(io_symbols)[:10],
            )
            features.io_apis.append(feat)

        nio_symbols = [c for c in all_referenced_classes if c.startswith("java/nio/file/")]
        if nio_symbols:
            feat = DetectedFeature(
                category="io",
                name="Java NIO File System (java.nio.file)",
                description="Modern NIO file path operations detected. Requires virtual filesystem in browser.",
                severity="warning",
                matched_symbols=sorted(nio_symbols)[:10],
            )
            features.io_apis.append(feat)

        # 5. Networking
        net_symbols = [c for c in all_referenced_classes if c.startswith("java/net/Socket") or c.startswith("java/net/ServerSocket")]
        if net_symbols:
            feat = DetectedFeature(
                category="network",
                name="Raw TCP/UDP Sockets (java.net.Socket)",
                description="Direct socket networking detected. Browsers cannot make raw TCP connections without WebSocket proxy.",
                severity="blocker",
                matched_symbols=sorted(net_symbols),
            )
            features.network_apis.append(feat)

        url_symbols = [c for c in all_referenced_classes if c in ("java/net/URL", "java/net/URI")]
        if url_symbols:
            feat = DetectedFeature(
                category="network",
                name="URL / Resource Loading (java.net.URL)",
                description="Resource resolution via URL (commonly used for getClass().getResource()).",
                severity="info",
                matched_symbols=sorted(url_symbols),
            )
            features.network_apis.append(feat)

        # 6. Reflection & Dynamic Invocation
        reflect_symbols = [c for c in all_referenced_classes if c.startswith("java/lang/reflect/")]
        if reflect_symbols:
            feat = DetectedFeature(
                category="reflection",
                name="Java Reflection (java.lang.reflect)",
                description="Dynamic reflection detected. AOT compilers like TeaVM require metadata preservation.",
                severity="warning",
                matched_symbols=sorted(reflect_symbols)[:10],
            )
            features.reflection_apis.append(feat)

        unsafe_symbols = [c for c in all_referenced_classes if "Unsafe" in c or c.startswith("jdk/internal/")]
        if unsafe_symbols:
            feat = DetectedFeature(
                category="reflection",
                name="sun.misc.Unsafe / Internal APIs",
                description="Low-level internal JVM unsafe operations detected. Blocked on most browser runtimes.",
                severity="blocker",
                matched_symbols=sorted(unsafe_symbols),
            )
            features.reflection_apis.append(feat)

        # 7. External / NetBeans Libraries
        nb_symbols = [c for c in all_referenced_classes if "org/netbeans/lib/awtextra" in c]
        if nb_symbols or any("AbsoluteLayout" in cp for cp in self.manifest_classpath):
            feat = DetectedFeature(
                category="external_library",
                name="NetBeans AbsoluteLayout",
                description="NetBeans visual GUI designer AbsoluteLayout library required.",
                severity="warning",
                matched_symbols=sorted(nb_symbols) or ["org/netbeans/lib/awtextra/AbsoluteLayout"],
            )
            features.external_libraries.append(feat)

        # 8. Native methods / calls
        native_calls = [f"{cls}.{m}" for cls, m in all_method_calls if cls == "java/lang/System" and m in ("load", "loadLibrary")]
        if has_native_methods or native_calls:
            feat = DetectedFeature(
                category="native",
                name="JNI / Native Code Binding",
                description="Class contains native method declarations or System.loadLibrary calls.",
                severity="blocker",
                matched_symbols=native_calls if native_calls else ["native method declaration"],
            )
            features.native_features.append(feat)

        # Aggregate
        all_list = (
            features.gui_frameworks
            + features.audio_apis
            + features.threading_apis
            + features.io_apis
            + features.network_apis
            + features.reflection_apis
            + features.external_libraries
            + features.native_features
        )
        features.all_features = all_list
        return features
