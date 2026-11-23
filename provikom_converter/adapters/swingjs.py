"""SwingJS Backend Adapter for Provikom Converter."""

from __future__ import annotations

from typing import Any, List

from provikom_converter.adapters.base import (
    BackendAdapter,
    BuildOptions,
    BuildResult,
    ConversionOptions,
    ConversionPlan,
    ConversionStep,
    UnsupportedRuntimeError,
)
from provikom_converter.analyzer.archive import ArchiveInventory
from provikom_converter.analyzer.compatibility import (
    BackendEvaluation,
    CompatibilityEvaluator,
    CompatibilityStatus,
)
from provikom_converter.analyzer.rules import AnalysisFeatures


class SwingJSAdapter(BackendAdapter):
    """Adapter for SwingJS (Java2Script) source-level transpiler."""

    @property
    def backend_id(self) -> str:
        return "swingjs"

    @property
    def display_name(self) -> str:
        return "SwingJS / Java2Script"

    @property
    def is_open_source(self) -> bool:
        return True

    @property
    def supports_bytecode_input(self) -> bool:
        return False

    @property
    def supports_source_input(self) -> bool:
        return True

    def evaluate_compatibility(
        self,
        inventory: ArchiveInventory,
        features: AnalysisFeatures,
        class_major_versions: List[int],
    ) -> BackendEvaluation:
        evaluator = CompatibilityEvaluator(inventory, features, class_major_versions)
        return evaluator.evaluate_swingjs()

    def create_conversion_plan(
        self,
        inventory: ArchiveInventory,
        features: AnalysisFeatures,
        class_major_versions: List[int],
        options: ConversionOptions,
    ) -> ConversionPlan:
        eval_result = self.evaluate_compatibility(inventory, features, class_major_versions)
        
        steps: List[ConversionStep] = [
            ConversionStep(
                name="Validate Java source project",
                description=(
                    "Inspect src/**/*.java, select one main class, and reject "
                    "unsupported dependencies, symlinks, and non-Java 8 source."
                ),
                automated=True,
            ),
            ConversionStep(
                name="Compile source with release 8",
                description="Compile the original Java source with the pinned JDK 17 javac --release 8.",
                automated=True,
            ),
            ConversionStep(
                name="Transpile with Java2Script",
                description=(
                    "Run the pinned Eclipse/Java2Script compiler and require "
                    "generated JavaScript for the selected main class."
                ),
                automated=True,
            ),
            ConversionStep(
                name="Package offline SwingJS artifact",
                description="Copy the pinned SwingJS runtime and write index.html, manifest, and ownership evidence.",
                automated=True,
            ),
            ConversionStep(
                name="Verify in Chromium",
                description="Run provikom verify-swingjs and require runtime evidence before publication.",
                automated=True,
                requires_user_input=False,
            ),
        ]

        return ConversionPlan(
            backend_id=self.backend_id,
            is_feasible=bool(eval_result.status != CompatibilityStatus.UNSUPPORTED),
            summary=eval_result.summary,
            steps=steps,
            required_tools=[
                "pinned-jdk-17",
                "eclipse-2024-03",
                "java2script-5.0.1-v7",
                "swingjs-runtime",
            ],
            estimated_difficulty="high",
        )

    def generate_artifact(
        self,
        analysis_result: Any,
        options: BuildOptions,
    ) -> BuildResult:
        raise UnsupportedRuntimeError(
            "SwingJS requires Java source input. Use `provikom build-project "
            "<source-directory> --output <directory>`; JAR decompilation is not "
            "supported."
        )

    def get_runtime_dependencies(self) -> List[str]:
        return [
            "swingjs/swingjs2.js",
        ]
