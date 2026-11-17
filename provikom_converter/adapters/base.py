"""Backend Adapter Interface Specification for Provikom Converter.

Defines the contract for browser runtime compilers, emulators, and transpilers.
Separates analysis, planning, conversion, and packaging into independently
maintainable components.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from provikom_converter.analyzer.archive import ArchiveInventory
from provikom_converter.analyzer.compatibility import BackendEvaluation
from provikom_converter.analyzer.rules import AnalysisFeatures


@dataclass
class ConversionOptions:
    """Options configuring artifact generation."""
    output_directory: str
    game_title: str
    auto_start: bool = True
    enable_audio: bool = True
    virtual_mount_root: str = "/str/"
    custom_heap_size_mb: int = 256
    extra_classpath: List[str] = field(default_factory=list)
    generate_standalone_html: bool = True


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
    def get_runtime_dependencies(self) -> List[str]:
        """List required browser scripts, CDNs, or runtime packages."""
        pass
