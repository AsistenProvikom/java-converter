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

            # Validate backend compatibility entries
            backends = report_dict["backend_compatibility"]
            for b_name in ("cheerpj", "teavm", "swingjs"):
                self.assertIn(b_name, backends)
                b_eval = backends[b_name]
                for req in self.schema["definitions"]["backendEvaluation"]["required"]:
                    self.assertIn(req, b_eval, f"Missing backendEvaluation field {req} in {b_name}")


if __name__ == "__main__":
    unittest.main()
