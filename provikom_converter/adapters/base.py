"""Backend Adapter Interface Specification for Provikom Converter.

Defines the contract for browser runtime compilers, emulators, and transpilers.
Separates analysis, planning, conversion, artifact generation, and packaging
into independently maintainable components.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from provikom_converter.analyzer.archive import ArchiveInventory
from provikom_converter.analyzer.compatibility import BackendEvaluation
from provikom_converter.analyzer.rules import AnalysisFeatures


class UnsupportedRuntimeError(Exception):
    """Raised when an archive's bytecode cannot be targeted by the backend runtime."""
    pass


class MissingDependencyError(Exception):
    """Raised when a required manifest Class-Path dependency is missing."""
    pass


@dataclass
class ConversionOptions:
    """Options configuring artifact generation."""
    output_directory: str
    game_title: str
    auto_start: bool = True
    enable_audio: bool = True
    virtual_mount_root: str = "/app/"
    custom_heap_size_mb: int = 256
    extra_classpath: List[str] = field(default_factory=list)
    generate_standalone_html: bool = True


@dataclass
class BuildOptions:
    """Options for building playable web artifacts."""
    output_directory: str
    backend: str = "cheerpj"
    game_title: Optional[str] = None
    force_overwrite: bool = False
    enable_audio: bool = True
    custom_heap_size_mb: int = 256
    virtual_mount_root: str = "/app/"
    source_jar_dir: Optional[str] = None


@dataclass
class StagedDependency:
    """Represents a resolved auxiliary dependency staged into the web artifact."""
    source_path: str
    relative_path: str
    virtual_path: str
    size_bytes: int


@dataclass
class BuildResult:
    """Result of building a playable web artifact."""
    backend_id: str
    output_directory: str
    entry_html: str
    game_jar_name: str
    game_title: str
    runtime_version: int
    runtime_label: str
    is_experimental: bool
    staged_dependencies: List[StagedDependency] = field(default_factory=list)
    generated_files: List[str] = field(default_factory=list)
    manifest_path: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ArtifactFile:
    relative_path: str
    content_type: str
    size_bytes: int
    description: str


@dataclass
class ConversionArtifact:
    """Represents the output of a conversion pipeline."""
    backend_id: str
    entry_html_path: str
    generated_files: List[ArtifactFile] = field(default_factory=list)
    external_cdn_dependencies: List[str] = field(default_factory=list)
    offline_capable: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversionStep:
    name: str
    description: str
    automated: bool
    requires_user_input: bool = False


@dataclass
class ConversionPlan:
    backend_id: str
    is_feasible: bool
    summary: str
    steps: List[ConversionStep] = field(default_factory=list)
    required_tools: List[str] = field(default_factory=list)
    estimated_difficulty: str = "low"  # 'trivial', 'low', 'medium', 'high', 'blocked'


class BackendAdapter(ABC):
    """Abstract specification for backend converters and runtimes."""

    @property
    @abstractmethod
    def backend_id(self) -> str:
        """Unique identifier (e.g., 'cheerpj', 'teavm', 'swingjs')."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name."""
        pass

    @property
    @abstractmethod
    def is_open_source(self) -> bool:
        """Whether the runtime/compiler is open-source."""
        pass

    @property
    @abstractmethod
    def supports_bytecode_input(self) -> bool:
        """Whether it accepts compiled .class / .jar files."""
        pass

    @property
    @abstractmethod
    def supports_source_input(self) -> bool:
        """Whether it accepts Java source files (.java)."""
        pass

    @abstractmethod
    def evaluate_compatibility(
        self,
        inventory: ArchiveInventory,
        features: AnalysisFeatures,
        class_major_versions: List[int],
    ) -> BackendEvaluation:
        """Produce a detailed compatibility assessment."""
        pass

    @abstractmethod
    def create_conversion_plan(
        self,
        inventory: ArchiveInventory,
        features: AnalysisFeatures,
        class_major_versions: List[int],
        options: ConversionOptions,
    ) -> ConversionPlan:
        """Plan the necessary steps for web conversion."""
        pass

    @abstractmethod
    def generate_artifact(
        self,
        analysis_result: Any,
        options: BuildOptions,
    ) -> BuildResult:
        """Generate a self-contained playable web artifact directory."""
        pass

    @abstractmethod
    def get_runtime_dependencies(self) -> List[str]:
        """List required browser scripts, CDNs, or runtime packages."""
        pass
