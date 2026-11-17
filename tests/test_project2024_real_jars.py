"""Integration test auditing the 7 real JAR files from project-2024."""

import os
import unittest
from pathlib import Path

from provikom_converter.analyzer.compatibility import CompatibilityStatus
from provikom_converter.orchestration.pipeline import ConverterPipeline
from tests.fixtures import find_project2024_games_dir, require_fixture


class TestProject2024RealJars(unittest.TestCase):
    GAMES_DIR = find_project2024_games_dir()

    EXPECTED_GAMES = {
        "CarTraffic.jar": {
            "main_class": "main.Main",
            "max_version": 66,
            "cheerpj_status": CompatibilityStatus.SUPPORTED,
        },
        "FrogieCrossTheRoad.jar": {
            "main_class": "main.Main",
            "max_version": 66,
            "cheerpj_status": CompatibilityStatus.SUPPORTED_WITH_WORKAROUNDS,
        },
        "Minesweeper.jar": {
            "main_class": "tugasakhir1.Start",
            "max_version": 66,
            "cheerpj_status": CompatibilityStatus.SUPPORTED_WITH_WORKAROUNDS,
        },
        "PaddleGame.jar": {
            "main_class": "keyboarddemo.LevelFrame",
            "max_version": 52,
            "cheerpj_status": CompatibilityStatus.SUPPORTED_WITH_WORKAROUNDS,
        },
        "PongGame.jar": {
            "main_class": "ucupandriska.ponggame.Main",
            "max_version": 65,
            "cheerpj_status": CompatibilityStatus.SUPPORTED_WITH_WORKAROUNDS,
        },
        "Snake Game FinPro.jar": {
            "main_class": "SnakeMain",
            "max_version": 66,
            "cheerpj_status": CompatibilityStatus.SUPPORTED,
        },
        "flappy.jar": {
            "main_class": "MainMenu",
            "max_version": 66,
            "cheerpj_status": CompatibilityStatus.SUPPORTED,
        },
    }

    def setUp(self):
        require_fixture(self.GAMES_DIR / "CarTraffic.jar", label="project-2024 games directory")

    def test_audit_all_seven_games(self):
        pipeline = ConverterPipeline()

        for filename, expected in self.EXPECTED_GAMES.items():
            jar_path = self.GAMES_DIR / filename
            self.assertTrue(jar_path.exists(), f"Game JAR missing: {filename}")

            res = pipeline.analyze_jar(jar_path)
            report = res.report

            # Assert manifest Main-Class was correctly extracted
            self.assertEqual(
                report.manifest.main_class,
                expected["main_class"],
                f"Mismatch in Main-Class for {filename}",
            )

            # Assert bytecode major version
            self.assertEqual(
                report.class_file_info.max_major_version,
                expected["max_version"],
                f"Mismatch in class major version for {filename}",
            )

            # Assert CheerpJ compatibility status
            cheerpj_eval = report.backend_compatibility["cheerpj"]
            self.assertEqual(
                cheerpj_eval["status"],
                expected["cheerpj_status"],
                f"Mismatch in CheerpJ status for {filename}",
            )

            # Assert TeaVM is marked unsupported for desktop Swing
            teavm_eval = report.backend_compatibility["teavm"]
            self.assertEqual(
                teavm_eval["status"],
                CompatibilityStatus.UNSUPPORTED,
                f"TeaVM should be unsupported for Swing game {filename}",
            )

            # Assert SwingJS requires source
            swingjs_eval = report.backend_compatibility["swingjs"]
            self.assertEqual(
                swingjs_eval["status"],
                CompatibilityStatus.REQUIRES_SOURCE,
                f"SwingJS should require source for bytecode {filename}",
            )


if __name__ == "__main__":
    unittest.main()
