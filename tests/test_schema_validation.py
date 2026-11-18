"""Tests verifying report structure against the JSON schema specification."""

import json
import unittest
from pathlib import Path

from provikom_converter.orchestration.pipeline import ConverterPipeline
from tests.fixtures import create_minimal_class_bytes, create_synthetic_jar


class TestSchemaValidation(unittest.TestCase):
    def setUp(self):
        self.schema_path = Path(__file__).parent.parent / "schema" / "compatibility-report.schema.json"
        self.schema = json.loads(self.schema_path.read_text(encoding="utf-8"))

    def test_schema_syntax(self):
        self.assertEqual(self.schema["$id"], "https://provikom.org/schema/v1/compatibility-report.json")
        self.assertIn("metadata", self.schema["required"])
        self.assertIn("backend_compatibility", self.schema["required"])
        # Additive in Milestone 2B: optional so 2A reports remain valid.
        self.assertIn("lifecycle", self.schema["properties"])
        self.assertNotIn("lifecycle", self.schema["required"])

    def test_artifact_manifest_schema_lifecycle(self):
        manifest_schema = json.loads(
            (Path(__file__).parent.parent / "schema" / "artifact-manifest.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest_schema["$id"], "https://provikom.org/schema/v1/artifact-manifest.json")
        # Version 1.0 manifests remain valid without a lifecycle block.
        self.assertNotIn("lifecycle", manifest_schema["required"])
        self.assertIn("ownership", manifest_schema["properties"])
        self.assertNotIn("ownership", manifest_schema["required"])
        conditionals = manifest_schema["allOf"]
        self.assertEqual(conditionals[0]["if"]["properties"]["schema_version"]["const"], "1.1")
        self.assertIn("lifecycle", conditionals[0]["then"]["required"])
        states = manifest_schema["definitions"]["lifecycle"]["properties"]["state"]["enum"]
        self.assertIn("runtime_verified", states)
        self.assertIn("failed", states)

    def test_demo_verification_evidence(self):
        root = Path(__file__).parent.parent
        expected = {
            "car-traffic": "runtime_verified",
            "flappy": "runtime_verified",
            "paddle-game": "runtime_verified",
            "pong-game": "failed",
        }
        for name, state in expected.items():
            manifest_path = root / "demo" / name / "manifest.json"
            record_path = root / "demo" / name / "verification.json"
            self.assertTrue(manifest_path.is_file(), manifest_path)
            self.assertTrue(record_path.is_file(), record_path)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            record = json.loads(record_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], "1.1")
            self.assertEqual(manifest["lifecycle"]["state"], state)
            self.assertEqual(manifest["lifecycle"]["execution_verified"], state == "runtime_verified")
            self.assertEqual(manifest["lifecycle"]["source"], "browser_verification")
            self.assertEqual(record["state"], state)
            self.assertEqual(record["artifact"], f"demo/{name}")
            self.assertEqual(record["artifact_jar_sha256"], manifest["game"]["sha256"])
            self.assertIn("verification.json", manifest["generated_files"])
            for screenshot in record["screenshots"]:
                self.assertTrue((root / screenshot).is_file(), screenshot)

    def test_generated_report_adherence(self):
        class_bytes = create_minimal_class_bytes(
            major_version=65,
            this_class_name="com/example/PongGame",
            referenced_classes=["javax/swing/JFrame", "javax/sound/sampled/Clip"],
        )
        jar_bytes = create_synthetic_jar(
            manifest_lines=["Manifest-Version: 1.0", "Main-Class: com.example.PongGame"],
            classes=[("com/example/PongGame.class", class_bytes)],
        )

        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".jar") as tmp:
            tmp.write(jar_bytes)
            tmp.flush()

            pipeline = ConverterPipeline()
            res = pipeline.analyze_jar(tmp.name)
            report_dict = res.report.to_dict()

            # Validate top-level required properties
            for req in self.schema["required"]:
                self.assertIn(req, report_dict, f"Missing required property: {req}")

            # Validate metadata
            meta = report_dict["metadata"]
            for req in self.schema["properties"]["metadata"]["required"]:
                self.assertIn(req, meta, f"Missing required metadata property: {req}")
            self.assertEqual(meta["tool_name"], "provikom-converter")
            self.assertEqual(len(meta["sha256"]), 64)

            lifecycle = report_dict["lifecycle"]
            self.assertEqual(lifecycle["state"], "analyzed")
            self.assertTrue(lifecycle["prediction_only"])
            self.assertFalse(lifecycle["execution_verified"])

            # Validate backend compatibility entries
            backends = report_dict["backend_compatibility"]
            for b_name in ("cheerpj", "teavm", "swingjs"):
                self.assertIn(b_name, backends)
                b_eval = backends[b_name]
                for req in self.schema["definitions"]["backendEvaluation"]["required"]:
                    self.assertIn(req, b_eval, f"Missing backendEvaluation field {req} in {b_name}")


if __name__ == "__main__":
    unittest.main()
