"""CheerpJ 5.0 Backend Adapter for Provikom Converter."""

from __future__ import annotations

from typing import List

from provikom_converter.adapters.base import (
    BackendAdapter,
    ConversionOptions,
    ConversionPlan,
    ConversionStep,
)
from provikom_converter.analyzer.archive import ArchiveInventory
from provikom_converter.analyzer.compatibility import (
    BackendEvaluation,
    CompatibilityEvaluator,
    CompatibilityStatus,
)
from provikom_converter.analyzer.rules import AnalysisFeatures


class CheerpJAdapter(BackendAdapter):
    """Adapter for Leaning Technologies CheerpJ JVM emulator."""

    @property
    def backend_id(self) -> str:
        return "cheerpj"

    @property
    def display_name(self) -> str:
        return "CheerpJ 5.0"

    @property
    def is_open_source(self) -> bool:
        return False

    @property
    def supports_bytecode_input(self) -> bool:
        return True

    @property
    def supports_source_input(self) -> bool:
        return False

    def evaluate_compatibility(
        self,
        inventory: ArchiveInventory,
        features: AnalysisFeatures,
        class_major_versions: List[int],
    ) -> BackendEvaluation:
        evaluator = CompatibilityEvaluator(inventory, features, class_major_versions)
        return evaluator.evaluate_cheerpj()

    def create_conversion_plan(
        self,
        inventory: ArchiveInventory,
        features: AnalysisFeatures,
        class_major_versions: List[int],
        options: ConversionOptions,
    ) -> ConversionPlan:
        eval_result = self.evaluate_compatibility(inventory, features, class_major_versions)
        is_feasible = eval_result.status in (
            CompatibilityStatus.SUPPORTED,
            CompatibilityStatus.SUPPORTED_WITH_WORKAROUNDS,
        )

        steps: List[ConversionStep] = []
        if is_feasible:
            steps.append(
                ConversionStep(
                    name="Stage Archive",
                    description="Copy main JAR to public web artifacts directory.",
                    automated=True,
                )
            )

            if inventory.manifest and inventory.manifest.class_path:
                steps.append(
                    ConversionStep(
                        name="Resolve Class-Path Dependencies",
                        description=f"Stage external dependencies: {inventory.manifest.class_path}",
                        automated=True,
                    )
                )

            steps.append(
                ConversionStep(
                    name="Generate HTML Launcher",
                    description="Generate responsive HTML5 web shell with CheerpJ 5.0 loader script.",
                    automated=True,
                )
            )
            steps.append(
                ConversionStep(
                    name="Synthesize Runtime Controller",
                    description="Generate script.js with cheerpjInit, cheerOSAddStringFile, and canvas mounting.",
                    automated=True,
                )
            )

        return ConversionPlan(
            backend_id=self.backend_id,
            is_feasible=is_feasible,
            summary=eval_result.summary,
            steps=steps,
            required_tools=["cheerpj-loader"],
            estimated_difficulty="trivial" if eval_result.status == CompatibilityStatus.SUPPORTED else "low",
        )

    def get_runtime_dependencies(self) -> List[str]:
        return [
            "https://cjrtnc.leaningtech.com/5.0/loader.js",
        ]
