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
        
        # When only JAR is available, decompilation is required
        steps: List[ConversionStep] = [
            ConversionStep(
                name="Decompile JAR to Java Source",
                description="Use CFR or Fernflower decompiler to extract .java source files from untrusted JAR.",
                automated=True,
            ),
            ConversionStep(
                name="Java Version Retargeting",
                description="Verify decompiled source conforms to Java 8/11 language syntax accepted by SwingJS.",
                automated=True,
                requires_user_input=False,
            ),
            ConversionStep(
                name="Transpile with Java2Script",
                description="Run Java2Script compiler to generate SwingJS JavaScript files (.js).",
                automated=True,
            ),
            ConversionStep(
                name="Bundle SwingJS Runtime",
                description="Include swingjs2.js and Java 8 Swing core JavaScript emulation library.",
                automated=True,
            ),
        ]

        return ConversionPlan(
            backend_id=self.backend_id,
            is_feasible=True,
            summary=eval_result.summary,
            steps=steps,
            required_tools=["cfr-decompiler", "java2script", "node"],
            estimated_difficulty="high",
        )

    def generate_artifact(
        self,
        analysis_result: Any,
        options: BuildOptions,
    ) -> BuildResult:
        raise NotImplementedError("SwingJS source transpilation artifact generation is scheduled for future milestones.")

    def get_runtime_dependencies(self) -> List[str]:
        return [
            "swingjs/swingjs2.js",
        ]
