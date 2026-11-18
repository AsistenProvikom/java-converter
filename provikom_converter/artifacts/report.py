"""Compatibility report generator and serializer for Provikom Converter."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from provikom_converter.analyzer.archive import ArchiveInventory
from provikom_converter.analyzer.bytecode import (
    ParsedClassFile,
    java_version_from_major,
)
from provikom_converter.analyzer.compatibility import BackendEvaluation
from provikom_converter.analyzer.rules import AnalysisFeatures, DetectedFeature
from provikom_converter.lifecycle import static_analysis_lifecycle
from provikom_converter.version import __version__


@dataclass
class ReportMetadata:
    tool_name: str
    tool_version: str
    analysis_timestamp: str
    target_file: str
    file_size_bytes: int
    sha256: str


@dataclass
class ArchiveSummaryData:
    total_entries: int
    total_classes: int
    total_resources: int
    total_native_libraries: int
    total_nested_archives: int
    total_uncompressed_bytes: int
    total_compressed_bytes: int
    resource_breakdown: Dict[str, int]
    security_warnings: List[str]


@dataclass
class ManifestData:
    main_class: Optional[str]
    class_path: List[str]
    created_by: Optional[str]
    build_jdk: Optional[str]
    raw_attributes: Dict[str, str]


@dataclass
class ClassFileInfoData:
    min_major_version: int
    max_major_version: int
    min_java_version: str
    max_java_version: str
    unique_major_versions: List[int]
    has_native_methods: bool


@dataclass
class RecommendationData:
    primary_backend: str
    secondary_backend: Optional[str]
    feasibility: str
    key_takeaways: List[str]


@dataclass
class LifecycleData:
    state: str
    prediction_only: bool
    execution_verified: bool
    source: str
    verification: Dict[str, Any]


@dataclass
class CompatibilityReport:
    schema_version: str
    metadata: ReportMetadata
    archive_summary: ArchiveSummaryData
    manifest: ManifestData
    class_file_info: ClassFileInfoData
    features_detected: Dict[str, List[Dict[str, Any]]]
    backend_compatibility: Dict[str, Dict[str, Any]]
    recommendation: RecommendationData
    lifecycle: LifecycleData

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


def calculate_sha256(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def build_report(
    filename: str,
    file_bytes: bytes,
    inventory: ArchiveInventory,
    parsed_classes: List[ParsedClassFile],
    features: AnalysisFeatures,
    evaluations: Dict[str, BackendEvaluation],
) -> CompatibilityReport:
    """Build a comprehensive, reproducible JSON compatibility report."""
    sha256 = calculate_sha256(file_bytes)
    now_iso = datetime.now(timezone.utc).isoformat()

    majors = [pc.major_version for pc in parsed_classes]
    min_maj = min(majors) if majors else 0
    max_maj = max(majors) if majors else 0
    unique_majors = sorted(list(set(majors)))
    has_native = any(pc.has_native_methods for pc in parsed_classes)

    meta = ReportMetadata(
        tool_name="provikom-converter",
        tool_version=__version__,
        analysis_timestamp=now_iso,
        target_file=filename,
        file_size_bytes=len(file_bytes),
        sha256=sha256,
    )

    summary = ArchiveSummaryData(
        total_entries=inventory.total_entries,
        total_classes=len(inventory.classes),
        total_resources=len(inventory.resources),
        total_native_libraries=len(inventory.native_libraries),
        total_nested_archives=len(inventory.nested_archives),
        total_uncompressed_bytes=inventory.total_uncompressed_bytes,
        total_compressed_bytes=inventory.total_compressed_bytes,
        resource_breakdown=inventory.resource_extensions,
        security_warnings=inventory.security_warnings,
    )

    manifest_info = inventory.manifest
    mf_data = ManifestData(
        main_class=manifest_info.main_class if manifest_info else None,
        class_path=manifest_info.class_path if manifest_info else [],
        created_by=manifest_info.created_by if manifest_info else None,
        build_jdk=manifest_info.build_jdk if manifest_info else None,
        raw_attributes=manifest_info.raw_attributes if manifest_info else {},
    )

    class_info = ClassFileInfoData(
        min_major_version=min_maj,
        max_major_version=max_maj,
        min_java_version=java_version_from_major(min_maj),
        max_java_version=java_version_from_major(max_maj),
        unique_major_versions=unique_majors,
        has_native_methods=has_native,
    )

    def feature_list(feats: List[DetectedFeature]) -> List[Dict[str, Any]]:
        return [asdict(f) for f in feats]

    feat_dict = {
        "gui_frameworks": feature_list(features.gui_frameworks),
        "audio_apis": feature_list(features.audio_apis),
        "threading_apis": feature_list(features.threading_apis),
        "io_apis": feature_list(features.io_apis),
        "network_apis": feature_list(features.network_apis),
        "reflection_apis": feature_list(features.reflection_apis),
        "external_libraries": feature_list(features.external_libraries),
        "native_features": feature_list(features.native_features),
    }

    backends_dict = {k: asdict(v) for k, v in evaluations.items()}

    # Formulate recommendation
    cheerpj_eval = evaluations.get("cheerpj")
    swingjs_eval = evaluations.get("swingjs")
    teavm_eval = evaluations.get("teavm")

    primary = "cheerpj"
    secondary = "swingjs"
    feasibility = "ready"
    takeaways: List[str] = []

    if cheerpj_eval and cheerpj_eval.blockers:
        feasibility = "blocked"
        takeaways.append(f"CheerpJ blocked: {'; '.join(cheerpj_eval.blockers)}")
    elif cheerpj_eval and cheerpj_eval.workarounds_needed:
        feasibility = "workaround_required"
        takeaways.extend(cheerpj_eval.workarounds_needed)
    else:
        takeaways.append("Can be directly published using CheerpJ 5.0 with zero source code modifications.")

    if swingjs_eval:
        takeaways.append("SwingJS is a viable open-source secondary path if source code is decompiled or provided.")

    if teavm_eval and teavm_eval.blockers:
        takeaways.append("TeaVM cannot be used directly due to missing desktop Swing/AWT runtime support.")

    rec = RecommendationData(
        primary_backend=primary,
        secondary_backend=secondary,
        feasibility=feasibility,
        key_takeaways=takeaways,
    )

    return CompatibilityReport(
        schema_version="https://provikom.org/schema/v1/compatibility-report.json",
        metadata=meta,
        archive_summary=summary,
        manifest=mf_data,
        class_file_info=class_info,
        features_detected=feat_dict,
        backend_compatibility=backends_dict,
        recommendation=rec,
        lifecycle=LifecycleData(**static_analysis_lifecycle()),
    )
