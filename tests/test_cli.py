"""Unit tests for the CLI interface."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from provikom_converter.cli import main
from tests.fixtures import create_minimal_class_bytes, create_synthetic_jar


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.jar_path = Path(self.temp_dir.name) / "test-game.jar"

        class_bytes = create_minimal_class_bytes(
            major_version=52,
            this_class_name="com/example/MyGame",
            referenced_classes=["javax/swing/JFrame"],
        )
        jar_bytes = create_synthetic_jar(
            manifest_lines=["Manifest-Version: 1.0", "Main-Class: com.example.MyGame"],
            classes=[("com/example/MyGame.class", class_bytes)],
        )
        self.jar_path.write_bytes(jar_bytes)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cli_version(self):
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            with self.assertRaises(SystemExit) as cm:
                main(["--version"])
            self.assertEqual(cm.exception.code, 0)
            self.assertIn("provikom-converter", fake_out.getvalue())

    def test_cli_analyze_human(self):
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            code = main(["analyze", str(self.jar_path)])
            self.assertEqual(code, 0)
            output = fake_out.getvalue()
            self.assertIn("PROVIKOM CONVERTER - COMPATIBILITY REPORT", output)
            self.assertIn("com.example.MyGame", output)
            self.assertIn("CheerpJ", output)

    def test_cli_analyze_json(self):
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            code = main(["analyze", str(self.jar_path), "--json"])
            self.assertEqual(code, 0)
            data = json.loads(fake_out.getvalue())
            self.assertEqual(data["manifest"]["main_class"], "com.example.MyGame")
            self.assertEqual(data["backend_compatibility"]["cheerpj"]["status"], "supported")

    def test_cli_analyze_missing_file(self):
        with patch("sys.stderr", new=io.StringIO()):
            code = main(["analyze", "/path/to/nonexistent.jar"])
            self.assertEqual(code, 1)

    def test_cli_schema(self):
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            code = main(["schema"])
            self.assertEqual(code, 0)
            schema = json.loads(fake_out.getvalue())
            self.assertEqual(schema["title"], "ProvikomCompatibilityReport")


if __name__ == "__main__":
    unittest.main()
