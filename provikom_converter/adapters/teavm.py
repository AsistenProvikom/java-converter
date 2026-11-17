"""TeaVM Backend Adapter for Provikom Converter."""

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


class TeaVMAdapter(BackendAdapter):
    """Adapter for TeaVM Ahead-of-Time Bytecode to JS/Wasm compiler."""

    @property
    def backend_id(self) -> str:
        return "teavm"

    @property
    def display_name(self) -> str:
        return "TeaVM (AOT Bytecode to JS/Wasm)"

    @property
    def is_open_source(self) -> bool:
        return True

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
        return evaluator.evaluate_teavm()

    def create_conversion_plan(
        self,
        inventory: ArchiveInventory,
        features: AnalysisFeatures,
        class_major_versions: List[int],
        options: ConversionOptions,
    ) -> ConversionPlan:
        eval_result = self.evaluate_compatibility(inventory, features, class_major_versions)
        is_feasible = eval_result.status == CompatibilityStatus.SUPPORTED

        steps: List[ConversionStep] = []
        if is_feasible:
            steps.append(
                ConversionStep(
                    name="Extract Classpath",
                    description="Extract class files and verify no missing transitive class definitions.",
                    automated=True,
                )
            )
            steps.append(
                ConversionStep(
                    name="Run TeaVM Compiler",
                    description="Compile Java bytecode directly to teavm.js or teavm.wasm using TeaVM toolchain.",
                    automated=True,
                )
            )
            steps.append(
                ConversionStep(
                    name="Generate HTML5 Host Shell",
                    description="Create minimal HTML harness mounting canvas and invoking main entry point.",
                    automated=True,
                )
            )
        else:
            steps.append(
                ConversionStep(
                    name="Refactor Desktop UI",
                    description="Replace javax.swing.* and java.awt.* with HTML5 Canvas or TeaVM Web API.",
                    automated=False,
                    requires_user_input=True,
                )
            )

        return ConversionPlan(
            backend_id=self.backend_id,
            is_feasible=is_feasible,
            summary=eval_result.summary,
            steps=steps,
            required_tools=["teavm-cli", "java-21-jdk"],
            estimated_difficulty="blocked" if not is_feasible else "medium",
        )

    def get_runtime_dependencies(self) -> List[str]:
        return []  # TeaVM produces self-contained JS/Wasm
