"""Tests for the source-backed SwingJS adapter and artifact safety."""

from __future__ import annotations

import functools
import http.server
import io
import json
import socketserver
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from provikom_converter.adapters.base import (
    BuildOptions,
    ConversionOptions,
    UnsupportedRuntimeError,
)
from provikom_converter.adapters.swingjs import SwingJSAdapter
from provikom_converter.analyzer.archive import ArchiveInventory
from provikom_converter.analyzer.rules import FeatureDetector
from provikom_converter.build_safety import (
    BuildPathError,
    _is_provikom_artifact,
    validate_source_output_directory,
)
from provikom_converter.cli import main
from provikom_converter.swingjs import pins
from provikom_converter.swingjs.builder import build_source_project
from provikom_converter.swingjs.source import (
    SourceProjectError,
    inspect_source_project,
)
from provikom_converter.swingjs.toolchain import (
    SwingJSToolchainError,
    resolve_toolchain,
)

ROOT = Path(__file__).resolve().parents[1]


def _write_project(root: Path, *, source: str, name: str = "Game.java") -> Path:
    package = root / "src" / "demo"
    package.mkdir(parents=True)
    (package / name).write_text(source, encoding="utf-8")
    return root


def _browser_ready() -> bool:
    try:
        import PIL  # noqa: F401
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return True


def _toolchain_ready() -> bool:
    try:
        resolve_toolchain()
    except SwingJSToolchainError:
        return False
    return True


class TestSourceInspection(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="provikom_source_")
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_single_main_class_and_source_hash(self):
        project = _write_project(
            self.tmp / "game",
            source="""package demo;
import javax.swing.JFrame;
public class Game {
    public static void main(String[] args) { new JFrame(); }
}
""",
        )
        inspected = inspect_source_project(project)
        self.assertEqual(inspected.main_class, "demo.Game")
        self.assertEqual(inspected.source_file_count, 1)
        self.assertEqual(len(inspected.source_sha256), 64)
        self.assertFalse(inspected.has_audio)

    def test_varargs_main_is_supported(self):
        project = _write_project(
            self.tmp / "game",
            source="""package demo;
public class Game { public static void main(String... args) { } }
""",
        )
        self.assertEqual(inspect_source_project(project).main_class, "demo.Game")

    def test_multiple_main_classes_require_selection(self):
        project = self.tmp / "game"
        _write_project(
            project,
            source="""package demo;
public class Game { public static void main(String[] args) { } }
""",
        )
        (project / "src" / "demo" / "Other.java").write_text(
            """package demo;
public class Other { public static void main(String[] args) { } }
""",
            encoding="utf-8",
        )
        with self.assertRaises(SourceProjectError):
            inspect_source_project(project)
        self.assertEqual(
            inspect_source_project(project, main_class="demo.Other").main_class,
            "demo.Other",
        )

    def test_missing_main_is_rejected(self):
        project = _write_project(
            self.tmp / "game",
            source="package demo; public class Game { }",
        )
        with self.assertRaises(SourceProjectError):
            inspect_source_project(project)

    def test_javafx_import_is_rejected(self):
        project = _write_project(
            self.tmp / "game",
            source="""package demo;
import javafx.application.Application;
public class Game { public static void main(String[] args) { } }
""",
        )
        with self.assertRaises(SourceProjectError) as raised:
            inspect_source_project(project)
        self.assertIn("JavaFX", str(raised.exception))

    def test_audio_import_is_recorded_as_warning(self):
        project = _write_project(
            self.tmp / "game",
            source="""package demo;
import javax.sound.sampled.AudioSystem;
public class Game { public static void main(String[] args) { } }
""",
        )
        inspected = inspect_source_project(project)
        self.assertTrue(inspected.has_audio)
        self.assertTrue(any("Audio" in warning for warning in inspected.warnings))

    def test_symlinked_source_project_is_rejected(self):
        project = _write_project(
            self.tmp / "game",
            source="package demo; public class Game { public static void main(String[] args) { } }",
        )
        link = self.tmp / "linked"
        link.symlink_to(project, target_is_directory=True)
        with self.assertRaises(SourceProjectError):
            inspect_source_project(link)


class TestSourceOutputSafety(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="provikom_source_safety_")
        self.tmp = Path(self._tmp.name)
        self.project = _write_project(
            self.tmp / "game",
            source="package demo; public class Game { public static void main(String[] args) { } }",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_project_cannot_be_output(self):
        with self.assertRaises(BuildPathError):
            validate_source_output_directory(self.project, self.project)

    def test_project_ancestor_cannot_be_output(self):
        with self.assertRaises(BuildPathError):
            validate_source_output_directory(self.project, self.tmp)

    def test_output_inside_project_is_allowed(self):
        _source, output = validate_source_output_directory(
            self.project, self.project / "build" / "artifact"
        )
        self.assertEqual(output, (self.project / "build" / "artifact").resolve())

    def test_symlink_output_is_rejected(self):
        target = self.tmp / "real-output"
        target.mkdir()
        link = self.tmp / "linked-output"
        link.symlink_to(target, target_is_directory=True)
        with self.assertRaises(BuildPathError):
            validate_source_output_directory(self.project, link)


class TestSwingJSAdapterContract(unittest.TestCase):
    def test_plan_does_not_claim_jar_decompilation(self):
        adapter = SwingJSAdapter()
        inventory = ArchiveInventory(
            total_entries=1,
            total_uncompressed_bytes=1,
            total_compressed_bytes=1,
            classes=["Game.class"],
        )
        plan = adapter.create_conversion_plan(
            inventory,
            FeatureDetector([], []).detect(),
            [52],
            ConversionOptions(output_directory="/tmp/out", game_title="Game"),
        )
        descriptions = " ".join(step.description for step in plan.steps).lower()
        self.assertNotIn("decompile", descriptions)
        self.assertIn("source", descriptions)
        self.assertIn("java2script-5.0.1-v7", plan.required_tools)

    def test_jar_input_requires_build_project(self):
        with self.assertRaises(UnsupportedRuntimeError) as raised:
            SwingJSAdapter().generate_artifact(
                None, BuildOptions(output_directory="/tmp/out")
            )
        self.assertIn("build-project", str(raised.exception))


class TestCLIErrors(unittest.TestCase):
    def test_build_project_missing_directory(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = main(["build-project", "/missing/source", "-o", "/tmp/out"])
        self.assertEqual(code, 1)
        self.assertIn("does not exist", stderr.getvalue())

    def test_verify_swingjs_missing_artifact(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = main(["verify-swingjs", "/missing/artifact"])
        self.assertEqual(code, 1)
        self.assertIn("does not exist", stderr.getvalue())


class TestPinnedManifest(unittest.TestCase):
    def test_pins_match_toolchain_manifest(self):
        manifest = json.loads(
            (ROOT / "tools" / "swingjs" / "toolchain_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["jdk"]["version"], pins.JDK_VERSION)
        self.assertEqual(manifest["eclipse"]["version"], pins.ECLIPSE_VERSION)
        self.assertEqual(manifest["java2script"]["commit"], pins.JAVA2SCRIPT_COMMIT)
        self.assertEqual(
            manifest["java2script"]["compiler_version"],
            pins.JAVA2SCRIPT_COMPILER_VERSION,
        )
        self.assertEqual(
            manifest["java2script"]["compiler_jar_sha256"],
            pins.JAVA2SCRIPT_COMPILER_SHA256,
        )
        self.assertEqual(
            manifest["java2script"]["runtime_zip_sha256"],
            pins.SWINGJS_RUNTIME_SHA256,
        )


@unittest.skipUnless(_toolchain_ready(), "pinned SwingJS toolchain is not installed")
class TestSwingJSBuildIntegration(unittest.TestCase):
    def _assert_source_artifact(self, source: Path, main_class: str, output: Path):
        result = build_source_project(source, output, title="Integration")
        self.assertEqual(result.backend_id, "swingjs")
        self.assertTrue((output / "index.html").is_file())
        self.assertTrue((output / "manifest.json").is_file())
        self.assertFalse((output / "verification.json").exists())
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["backend"], "swingjs")
        self.assertEqual(manifest["source_project"]["main_class"], main_class)
        self.assertGreaterEqual(manifest["source_project"]["source_file_count"], 1)
        generated = output / manifest["source_project"]["generated_js"]
        self.assertGreater(generated.stat().st_size, 1000)
        self.assertIn(b"Clazz.newClass", generated.read_bytes())
        self.assertTrue(_is_provikom_artifact(output))

    def test_poc_build_is_owned_and_source_derived(self):
        with tempfile.TemporaryDirectory(prefix="provikom_swingjs_build_") as tmp:
            self._assert_source_artifact(
                ROOT / "examples" / "swing-poc",
                "poc.SwingPoc",
                Path(tmp) / "poc-artifact",
            )

    def test_second_widget_fixture_builds_with_different_swing_apis(self):
        with tempfile.TemporaryDirectory(prefix="provikom_swingjs_widgets_") as tmp:
            self._assert_source_artifact(
                ROOT / "examples" / "swing-widgets",
                "compat.WidgetDemo",
                Path(tmp) / "widget-artifact",
            )

    def test_generated_javascript_is_reproducible(self):
        with tempfile.TemporaryDirectory(prefix="provikom_swingjs_repro_") as tmp:
            first = Path(tmp) / "first"
            second = Path(tmp) / "second"
            result = build_source_project(ROOT / "examples" / "swing-poc", first)
            build_source_project(ROOT / "examples" / "swing-poc", second)
            generated = result.metadata["generated_js"]
            self.assertEqual(
                (first / generated).read_bytes(),
                (second / generated).read_bytes(),
            )

    @unittest.skipUnless(_browser_ready(), "Playwright/Pillow are not installed")
    def test_artifact_loads_below_a_portal_subdirectory(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            self.skipTest(str(exc))

        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, fmt, *args):
                pass

        with tempfile.TemporaryDirectory(prefix="provikom_swingjs_portal_") as tmp:
            portal = Path(tmp) / "portal"
            artifact = portal / "web-games" / "demo"
            build_source_project(ROOT / "examples" / "swing-poc", artifact)

            socketserver.ThreadingTCPServer.allow_reuse_address = True
            server = socketserver.ThreadingTCPServer(
                ("127.0.0.1", 0),
                functools.partial(QuietHandler, directory=str(portal)),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
                    page = browser.new_page(viewport={"width": 1280, "height": 900})
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(
                        "http://127.0.0.1:{}/web-games/demo/index.html".format(
                            server.server_address[1]
                        ),
                        wait_until="load",
                        timeout=60000,
                    )
                    page.wait_for_selector("canvas", timeout=60000)
                    page.wait_for_timeout(1000)
                    self.assertFalse(errors, errors)
                    self.assertTrue(page.locator("canvas").first.is_visible())
                    browser.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
