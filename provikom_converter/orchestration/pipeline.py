"""Orchestration pipeline coordinating analysis and report generation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from provikom_converter.analyzer.archive import (
    ArchiveInventory,
    SafeArchiveReader,
)
from provikom_converter.analyzer.bytecode import ClassFileReader, ParsedClassFile
from provikom_converter.analyzer.compatibility import (
    BackendEvaluation,
    CompatibilityEvaluator,
)
from provikom_converter.analyzer.rules import AnalysisFeatures, FeatureDetector
from provikom_converter.artifacts.report import CompatibilityReport, build_report


@dataclass
class AnalysisResult:
    target_path: str
    inventory: ArchiveInventory
    parsed_classes: List[ParsedClassFile]
    features: AnalysisFeatures
    evaluations: Dict[str, BackendEvaluation]
    report: CompatibilityReport


class ConverterPipeline:
    """End-to-end coordinator for Java archive analysis and compatibility checks."""

    def analyze_jar(self, jar_path: str | Path) -> AnalysisResult:
        jar_path = Path(jar_path).resolve()
        if not jar_path.exists():
            raise FileNotFoundError(f"File not found: {jar_path}")
        if not jar_path.is_file():
            raise ValueError(f"Path is not a regular file: {jar_path}")

        file_bytes = jar_path.read_bytes()
        reader = SafeArchiveReader(file_bytes, name=jar_path.name)
        zf, inventory = reader.inspect()

        parsed_classes: List[ParsedClassFile] = []
        try:
            for class_entry in inventory.classes:
                try:
                    class_data = zf.read(class_entry)
                    parser = ClassFileReader(class_data, filename=class_entry)
                    parsed = parser.parse()
                    parsed_classes.append(parsed)
                except Exception as e:
                    inventory.security_warnings.append(
                        f"Failed to parse class bytecode in '{class_entry}': {e}"
                    )
        finally:
            zf.close()

        # Run feature detection
        detector = FeatureDetector(
            parsed_classes,
            inventory.manifest.class_path if inventory.manifest else [],
        )
        features = detector.detect()

        # Run compatibility evaluations
        majors = [pc.major_version for pc in parsed_classes]
        evaluator = CompatibilityEvaluator(inventory, features, majors)
        evaluations = evaluator.evaluate_all()

        # Build formal report
        report = build_report(
            filename=jar_path.name,
            file_bytes=file_bytes,
            inventory=inventory,
            parsed_classes=parsed_classes,
            features=features,
            evaluations=evaluations,
        )

        return AnalysisResult(
            target_path=str(jar_path),
            inventory=inventory,
            parsed_classes=parsed_classes,
            features=features,
            evaluations=evaluations,
            report=report,
        )

    def analyze_batch(self, jar_paths: List[str | Path]) -> List[AnalysisResult]:
        results: List[AnalysisResult] = []
        for p in jar_paths:
            res = self.analyze_jar(p)
            results.append(res)
        return results
