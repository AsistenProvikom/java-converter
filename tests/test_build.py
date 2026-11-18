"""Unit and integration tests for the Milestone 2A CheerpJ builder.

These tests cover:
  - CheerpJ runtime version selection
  - Artifact generation and manifest contents
  - Manifest Class-Path dependency staging
  - Overwrite and error handling
  - HTTP Range Request server behaviour

Real project JARs are used when available. Set PROVIKOM_GAMES_DIR to point at a
different archive directory. Tests requiring missing archives are skipped.
"""

from __future__ import annotations

import hashlib
import http.client
import http.server
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

from provikom_converter.adapters.base import (
    BuildOptions,
    MissingDependencyError,
    UnsupportedRuntimeError,
)
from provikom_converter.adapters.cheerpj import CheerpJAdapter, select_cheerpj_runtime
from provikom_converter.adapters.swingjs import SwingJSAdapter
from provikom_converter.adapters.teavm import TeaVMAdapter
from provikom_converter.orchestration.pipeline import ConverterPipeline
from provikom_converter.server import RangeRequestHandler
from tests.fixtures import (
    create_minimal_class_bytes,
    create_synthetic_jar,
    find_project2024_games_dir,
    require_fixture,
)

GAMES_DIR = find_project2024_games_dir()
PONG_JAR = GAMES_DIR / "PongGame.jar"
FLAPPY_JAR = GAMES_DIR / "flappy.jar"
CARTRAFFIC_JAR = GAMES_DIR / "CarTraffic.jar"
PADDLE_JAR = GAMES_DIR / "PaddleGame.jar"


def _require(path: Path) -> None:
    require_fixture(path, label="game archive")


class TestSelectCheerpJRuntime(unittest.TestCase):
    def test_java8_boundaries(self):
        for major in (45, 49, 52):
            version, _, experimental = select_cheerpj_runtime(major)
            self.assertEqual(version, 8)
            self.assertFalse(experimental)

    def test_java9_to_21_use_java21_runtime(self):
        for major in (53, 55, 61, 65):
            version, label, experimental = select_cheerpj_runtime(major)
            self.assertEqual(version, 21)
            self.assertIn("21", label)
            self.assertFalse(experimental)

    def test_java22_uses_experimental_java25_preview(self):
        version, label, experimental = select_cheerpj_runtime(66)
        self.assertEqual(version, 25)
        self.assertTrue(experimental)
        self.assertIn("experimental", label.lower())

    def test_unknown_versions_are_rejected(self):
        for major in (44, 67, 70, 100):
            with self.assertRaises(UnsupportedRuntimeError):
                select_cheerpj_runtime(major)


class TestPongArtifactGeneration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _require(PONG_JAR)
        cls._tmp = tempfile.TemporaryDirectory(prefix="provikom_pong_")
        cls.out = Path(cls._tmp.name) / "artifact"
        cls.result = ConverterPipeline().build_artifact(
            jar_path=PONG_JAR,
            backend="cheerpj",
            output_dir=cls.out,
            force_overwrite=False,
        )
        cls.manifest = json.loads((cls.out / "manifest.json").read_text(encoding="utf-8"))
        cls.html = (cls.out / "index.html").read_text(encoding="utf-8")
        cls.js = (cls.out / "app.js").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_expected_files_exist(self):
        for name in ("index.html", "style.css", "app.js", "manifest.json", "PongGame.jar"):
            self.assertTrue((self.out / name).is_file(), name)

    def test_runtime_is_java21(self):
        self.assertEqual(self.manifest["runtime_version"], 21)
        self.assertFalse(self.manifest["is_experimental"])
        self.assertEqual(self.manifest["runtime"]["version"], 21)

    def test_entry_point_and_metadata(self):
        self.assertEqual(self.manifest["entry_point"], "index.html")
        self.assertEqual(self.manifest["jar_file"], "PongGame.jar")
        self.assertEqual(self.manifest["java_major_version"], 65)
        self.assertEqual(self.manifest["game"]["main_class"], "ucupandriska.ponggame.Main")
        self.assertEqual(self.manifest["game"]["entry_point_source"], "manifest")
        self.assertTrue(self.manifest["game"]["has_audio"])

    def test_compatibility_metadata_present(self):
        compatibility = self.manifest["compatibility"]
        self.assertEqual(compatibility["status"], "supported_with_workarounds")
        self.assertTrue(compatibility["workarounds_needed"])
        self.assertTrue(any("audio" in risk.lower() for risk in compatibility["assumptions_and_risks"]))

    def test_html_uses_cheerpj_loader_and_escapes_title(self):
        self.assertIn("https://cjrtnc.leaningtech.com/5.0/loader.js", self.html)
        self.assertIn('id="btn-start"', self.html)
        self.assertIn('id="overlay-loading"', self.html)
        self.assertIn('id="overlay-error"', self.html)
        self.assertIn('id="btn-retry"', self.html)
        self.assertIn('id="cheerpj-display"', self.html)
        self.assertIn("Pong Game", self.html)

    def test_js_uses_official_app_mount_and_apis(self):
        self.assertIn("cheerpjInit", self.js)
        self.assertIn("cheerpjCreateDisplay", self.js)
        self.assertIn("cheerpjRunMain", self.js)
        self.assertIn('"virtualMountRoot": "/app/"', self.js)
        self.assertIn('"classPath"', self.js)
        self.assertIn("/app/PongGame.jar", self.js)
        self.assertNotIn('"/str/"', self.js)

    def test_original_jar_is_preserved(self):
        source_hash = hashlib.sha256(PONG_JAR.read_bytes()).hexdigest()
        staged_hash = hashlib.sha256((self.out / "PongGame.jar").read_bytes()).hexdigest()
        self.assertEqual(source_hash, staged_hash)
        self.assertEqual(source_hash, self.manifest["game"]["sha256"])


class TestJava22ArtifactGeneration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _require(CARTRAFFIC_JAR)
        cls._tmp = tempfile.TemporaryDirectory(prefix="provikom_cartraffic_")
        cls.out = Path(cls._tmp.name) / "artifact"
        cls.result = ConverterPipeline().build_artifact(
            jar_path=CARTRAFFIC_JAR,
            backend="cheerpj",
            output_dir=cls.out,
            force_overwrite=False,
        )
        cls.manifest = json.loads((cls.out / "manifest.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_experimental_runtime_selected(self):
        self.assertEqual(self.manifest["runtime_version"], 25)
        self.assertTrue(self.manifest["is_experimental"])
        self.assertIn("experimental", self.manifest["runtime"]["label"].lower())

    def test_manifest_round_trip_matches_result(self):
        self.assertEqual(self.result.game_title, self.manifest["game"]["title"])
        self.assertEqual(self.result.runtime_version, self.manifest["runtime_version"])


class TestDependencyStaging(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _require(PADDLE_JAR)
        cls._tmp = tempfile.TemporaryDirectory(prefix="provikom_paddle_")
        cls.out = Path(cls._tmp.name) / "artifact"
        cls.result = ConverterPipeline().build_artifact(
            jar_path=PADDLE_JAR,
            backend="cheerpj",
            output_dir=cls.out,
            force_overwrite=False,
        )
        cls.manifest = json.loads((cls.out / "manifest.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_dependency_is_staged_at_manifest_path(self):
        staged = self.out / "lib" / "AbsoluteLayout.jar"
        self.assertTrue(staged.is_file())
        self.assertEqual(staged.read_bytes()[:2], b"PK")

    def test_dependency_manifest_record_and_virtual_path(self):
        deps = self.manifest["dependencies"]
        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0]["relative_path"], "lib/AbsoluteLayout.jar")
        self.assertEqual(deps[0]["virtual_path"], "/app/lib/AbsoluteLayout.jar")
        self.assertGreater(deps[0]["size_bytes"], 0)

    def test_explicit_classpath_includes_dependency(self):
        self.assertEqual(
            self.manifest["paths"]["class_path"],
            ["/app/PaddleGame.jar", "/app/lib/AbsoluteLayout.jar"],
        )


class TestOverwriteAndErrors(unittest.TestCase):
    def test_force_removes_stale_files(self):
        _require(PONG_JAR)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "artifact"
            out.mkdir()
            (out / "stale.txt").write_text("old", encoding="utf-8")
            ConverterPipeline().build_artifact(
                jar_path=PONG_JAR, output_dir=out, force_overwrite=True
            )
            self.assertFalse((out / "stale.txt").exists())
            self.assertTrue((out / "index.html").is_file())

    def test_existing_non_empty_directory_requires_force(self):
        _require(PONG_JAR)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "artifact"
            out.mkdir()
            (out / "stale.txt").write_text("old", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                ConverterPipeline().build_artifact(
                    jar_path=PONG_JAR, output_dir=out, force_overwrite=False
                )

    def test_unsupported_bytecode_is_rejected(self):
        class_bytes = create_minimal_class_bytes(major_version=70)
        jar_bytes = create_synthetic_jar(
            manifest_lines=["Manifest-Version: 1.0", "Main-Class: Example"],
            classes=[("Example.class", class_bytes)],
        )
        with tempfile.TemporaryDirectory() as tmp:
            jar = Path(tmp) / "future.jar"
            jar.write_bytes(jar_bytes)
            with self.assertRaises(UnsupportedRuntimeError):
                ConverterPipeline().build_artifact(jar, Path(tmp) / "out")

    def test_missing_manifest_dependency_is_rejected(self):
        class_bytes = create_minimal_class_bytes(major_version=52)
        jar_bytes = create_synthetic_jar(
            manifest_lines=[
                "Manifest-Version: 1.0",
                "Main-Class: Example",
                "Class-Path: lib/DoesNotExist.jar",
            ],
            classes=[("Example.class", class_bytes)],
        )
        with tempfile.TemporaryDirectory() as tmp:
            jar = Path(tmp) / "missing-dep.jar"
            jar.write_bytes(jar_bytes)
            with self.assertRaises(MissingDependencyError):
                ConverterPipeline().build_artifact(jar, Path(tmp) / "out")

    def test_dependency_path_traversal_is_rejected(self):
        class_bytes = create_minimal_class_bytes(major_version=52)
        jar_bytes = create_synthetic_jar(
            manifest_lines=[
                "Manifest-Version: 1.0",
                "Main-Class: Example",
                "Class-Path: ../../evil.jar",
            ],
            classes=[("Example.class", class_bytes)],
        )
        with tempfile.TemporaryDirectory() as tmp:
            jar = Path(tmp) / "traversal.jar"
            jar.write_bytes(jar_bytes)
            with self.assertRaises(MissingDependencyError):
                ConverterPipeline().build_artifact(jar, Path(tmp) / "out")


class TestAdapterContract(unittest.TestCase):
    def test_cheerpj_implements_build_interface(self):
        self.assertTrue(callable(getattr(CheerpJAdapter, "generate_artifact")))
        self.assertEqual(CheerpJAdapter().get_runtime_dependencies(), [
            "https://cjrtnc.leaningtech.com/5.0/loader.js"
        ])

    def test_other_backends_are_not_implemented_yet(self):
        options = BuildOptions(output_directory="/tmp/x")
        for adapter in (TeaVMAdapter(), SwingJSAdapter()):
            with self.assertRaises(NotImplementedError):
                adapter.generate_artifact(None, options)


class TestRangeRequestServer(unittest.TestCase):
    PORT = 18085
    PAYLOAD = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="provikom_range_")
        (Path(cls._tmp.name) / "test.bin").write_bytes(cls.PAYLOAD)

        class Handler(RangeRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=cls._tmp.name, **kwargs)

            def log_message(self, fmt, *args):
                pass

        cls._server = http.server.ThreadingHTTPServer(("127.0.0.1", cls.PORT), Handler)
        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()
        time.sleep(0.2)

    @classmethod
    def tearDownClass(cls):
        cls._server.shutdown()
        cls._server.server_close()
        cls._tmp.cleanup()

    def _request(self, method="GET", headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.PORT, timeout=5)
        conn.request(method, "/test.bin", headers=headers or {})
        response = conn.getresponse()
        body = response.read()
        status = response.status
        response_headers = dict(response.getheaders())
        conn.close()
        return status, response_headers, body

    def test_full_file(self):
        status, headers, body = self._request()
        self.assertEqual(status, 200)
        self.assertEqual(body, self.PAYLOAD)
        self.assertEqual(headers["Accept-Ranges"], "bytes")
        self.assertEqual(headers["Content-Length"], str(len(self.PAYLOAD)))

    def test_head_request(self):
        status, headers, body = self._request("HEAD")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")
        self.assertEqual(headers["Content-Length"], str(len(self.PAYLOAD)))

    def test_prefix_range(self):
        status, headers, body = self._request(headers={"Range": "bytes=0-3"})
        self.assertEqual(status, 206)
        self.assertEqual(body, b"ABCD")
        self.assertEqual(headers["Content-Range"], f"bytes 0-3/{len(self.PAYLOAD)}")

    def test_suffix_range(self):
        status, headers, body = self._request(headers={"Range": "bytes=-4"})
        self.assertEqual(status, 206)
        self.assertEqual(body, b"WXYZ")
        self.assertEqual(headers["Content-Range"], f"bytes 22-25/{len(self.PAYLOAD)}")

    def test_open_ended_range(self):
        status, headers, body = self._request(headers={"Range": "bytes=20-"})
        self.assertEqual(status, 206)
        self.assertEqual(body, b"UVWXYZ")

    def test_unsatisfiable_range(self):
        status, headers, body = self._request(headers={"Range": "bytes=100-200"})
        self.assertEqual(status, 416)
        self.assertEqual(headers["Content-Range"], f"bytes */{len(self.PAYLOAD)}")
        self.assertEqual(body, b"")


if __name__ == "__main__":
    unittest.main(verbosity=2)
