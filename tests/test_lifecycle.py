"""Tests for lifecycle separation between predictions and runtime evidence."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from provikom_converter.lifecycle import (
    LIFECYCLE_STATES,
    apply_verification_to_manifest,
    built_artifact_lifecycle,
    make_verification_record,
    static_analysis_lifecycle,
)
from provikom_converter.orchestration.pipeline import ConverterPipeline
from tests.fixtures import create_minimal_class_bytes, create_synthetic_jar


class TestLifecycleStates(unittest.TestCase):
    def test_expected_states_are_defined(self):
        self.assertEqual(
            set(LIFECYCLE_STATES),
            {"analyzed", "candidate", "built", "runtime_verified", "failed", "unsupported"},
        )

    def test_static_analysis_is_prediction_only(self):
        block = static_analysis_lifecycle()
        self.assertEqual(block["state"], "analyzed")
        self.assertTrue(block["prediction_only"])
        self.assertFalse(block["execution_verified"])

    def test_built_artifact_is_not_runtime_verified(self):
        block = built_artifact_lifecycle()
        self.assertEqual(block["state"], "built")
        self.assertTrue(block["prediction_only"])
        self.assertFalse(block["execution_verified"])
        self.assertEqual(block["verification"]["state"], "not_run")

    def test_verification_record_rejects_non_execution_states(self):
        with self.assertRaises(ValueError):
            make_verification_record(
                game="Example",
                artifact="example",
                state="built",
                checks=[],
            )


class TestGeneratedLifecycleMetadata(unittest.TestCase):
    def _build(self, tmp: Path) -> Path:
        jar = tmp / "game.jar"
        jar.write_bytes(
            create_synthetic_jar(
                manifest_lines=["Manifest-Version: 1.0", "Main-Class: Example"],
                classes=[("Example.class", create_minimal_class_bytes(major_version=52))],
            )
        )
        out = tmp / "out"
        ConverterPipeline().build_artifact(jar, out)
        return out

    def test_analysis_report_is_analyzed(self):
        jar = Path(tempfile.mkdtemp(prefix="provikom_lifecycle_")) / "game.jar"
        jar.write_bytes(
            create_synthetic_jar(
                manifest_lines=["Manifest-Version: 1.0", "Main-Class: Example"],
                classes=[("Example.class", create_minimal_class_bytes(major_version=52))],
            )
        )
        report = ConverterPipeline().analyze_jar(jar).report.to_dict()
        self.assertEqual(report["lifecycle"]["state"], "analyzed")
        self.assertTrue(report["lifecycle"]["prediction_only"])
        self.assertFalse(report["lifecycle"]["execution_verified"])

    def test_manifest_is_built_not_runtime_verified(self):
        with tempfile.TemporaryDirectory(prefix="provikom_lifecycle_") as tmp:
            out = self._build(Path(tmp))
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], "1.1")
            self.assertEqual(manifest["lifecycle"]["state"], "built")
            self.assertTrue(manifest["lifecycle"]["prediction_only"])
            self.assertFalse(manifest["lifecycle"]["execution_verified"])
            self.assertEqual(manifest["lifecycle"]["verification"]["state"], "not_run")
            # Static prediction must remain untouched by lifecycle metadata.
            self.assertIn("status", manifest["compatibility"])

    def test_verification_updates_manifest_and_writes_record(self):
        with tempfile.TemporaryDirectory(prefix="provikom_lifecycle_") as tmp:
            out = self._build(Path(tmp))
            record = make_verification_record(
                game="Example",
                artifact=str(out),
                state="runtime_verified",
                checks=[{"name": "render", "passed": True}],
                screenshots=["docs/screenshots/example.png"],
            )
            manifest = apply_verification_to_manifest(out, record)

            self.assertEqual(manifest["lifecycle"]["state"], "runtime_verified")
            self.assertTrue(manifest["lifecycle"]["execution_verified"])
            self.assertFalse(manifest["lifecycle"]["prediction_only"])
            self.assertEqual(manifest["lifecycle"]["verification"]["record"], "verification.json")
            self.assertTrue((out / "verification.json").is_file())
            self.assertIn("verification.json", manifest["generated_files"])
            self.assertIn("status", manifest["compatibility"])

    def test_failed_verification_keeps_artifact_available(self):
        with tempfile.TemporaryDirectory(prefix="provikom_lifecycle_") as tmp:
            out = self._build(Path(tmp))
            record = make_verification_record(
                game="Pong",
                artifact=str(out),
                state="failed",
                checks=[{"name": "audio", "passed": False}],
                runtime_diagnostics=["No line matching interface Clip"],
            )
            manifest = apply_verification_to_manifest(out, record)
            self.assertEqual(manifest["lifecycle"]["state"], "failed")
            self.assertFalse(manifest["lifecycle"]["execution_verified"])
            self.assertTrue((out / "index.html").is_file())
            self.assertTrue((out / "verification.json").is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
