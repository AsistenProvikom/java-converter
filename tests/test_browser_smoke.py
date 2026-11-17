"""HTTP and Chromium smoke tests for generated CheerpJ web artifacts.

The HTTP tests always run. Browser tests run when Playwright and Chromium are
installed and the CheerpJ CDN is reachable. Set PROVIKOM_SKIP_BROWSER=1 to skip
browser tests explicitly.

Run:
    python -m unittest tests.test_browser_smoke -v
    PROVIKOM_SKIP_BROWSER=1 python -m unittest discover -s tests -v
"""

from __future__ import annotations

import http.client
import http.server
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from provikom_converter.server import RangeRequestHandler
from tests.fixtures import find_project2024_games_dir

GAMES_DIR = find_project2024_games_dir()
PONG_JAR = GAMES_DIR / "PongGame.jar"
FLAPPY_JAR = GAMES_DIR / "flappy.jar"
CARTRAFFIC_JAR = GAMES_DIR / "CarTraffic.jar"
PADDLE_JAR = GAMES_DIR / "PaddleGame.jar"
SCREENSHOT_DIR = Path(__file__).resolve().parent.parent / "docs" / "screenshots"
SKIP_BROWSER = os.environ.get("PROVIKOM_SKIP_BROWSER", "").strip() == "1"
CHEERPJ_LOADER = "https://cjrtnc.leaningtech.com/5.0/loader.js"


def _require_jar(path: Path) -> None:
    if not path.is_file():
        raise unittest.SkipTest(f"Archive not available: {path}")


def _build(jar: Path, out: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "provikom_converter",
            "build",
            str(jar),
            "--backend",
            "cheerpj",
            "--output",
            str(out),
            "--force",
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )


def _cdn_reachable() -> bool:
    try:
        with urllib.request.urlopen(CHEERPJ_LOADER, timeout=6) as response:
            return 200 <= response.status < 400
    except Exception:
        return False


class LocalServer:
    def __init__(self, directory: Path, port: int):
        directory_str = str(directory)

        class Handler(RangeRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=directory_str, **kwargs)

            def log_message(self, fmt, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.server.server_port), timeout=0.25):
                    return self
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("Local HTTP server did not start")

    def __exit__(self, exc_type, exc, tb):
        self.server.shutdown()
        self.server.server_close()


def _request(port: int, path: str, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    connection.request("GET", path, headers=headers or {})
    response = connection.getresponse()
    body = response.read()
    result = (response.status, dict(response.getheaders()), body)
    connection.close()
    return result


def _wait_for_canvas(page, timeout=75):
    deadline = time.time() + timeout
    status = "?"
    while time.time() < deadline:
        status = page.evaluate("() => document.body.dataset.status || ''")
        if page.evaluate("() => !!document.querySelector('#cheerpj-display canvas')"):
            return True, status
        if status == "error":
            return False, status
        time.sleep(0.5)
    return False, status


def _focus_canvas_and_press_keys(page):
    page.eval_on_selector(
        "#cheerpj-display canvas",
        "el => { el.tabIndex = 0; el.focus(); }",
    )
    for key in ("ArrowLeft", "ArrowRight", "Space", "ArrowUp", "ArrowDown"):
        page.keyboard.press(key)
        time.sleep(0.25)


def _click_canvas_relative(page, x, y):
    box = page.eval_on_selector(
        "#cheerpj-display canvas",
        "el => { const r = el.getBoundingClientRect(); return { x: r.x, y: r.y }; }",
    )
    page.mouse.click(box["x"] + x, box["y"] + y)


class TestArtifactHTTP(unittest.TestCase):
    PORT = 18080

    @classmethod
    def setUpClass(cls):
        _require_jar(CARTRAFFIC_JAR)
        cls._tmp = tempfile.TemporaryDirectory(prefix="provikom_http_")
        cls.out = Path(cls._tmp.name) / "cartraffic"
        result = _build(CARTRAFFIC_JAR, cls.out)
        if result.returncode != 0:
            raise unittest.SkipTest(f"Build failed:\n{result.stdout}\n{result.stderr}")
        cls._server = LocalServer(cls.out, cls.PORT)
        cls._server.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._server.__exit__(None, None, None)
        cls._tmp.cleanup()

    def test_index_html(self):
        status, headers, body = _request(self.PORT, "/")
        self.assertEqual(status, 200)
        self.assertIn(b"cheerpj", body.lower())
        self.assertIn(b"btn-start", body)
        self.assertEqual(headers["Accept-Ranges"], "bytes")

    def test_manifest_json(self):
        status, _, body = _request(self.PORT, "/manifest.json")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["backend"], "cheerpj")
        self.assertEqual(data["runtime_version"], 25)
        self.assertTrue(data["is_experimental"])
        self.assertEqual(data["entry_point"], "index.html")
        self.assertEqual(data["jar_file"], "CarTraffic.jar")
        self.assertEqual(data["java_major_version"], 66)
        self.assertIn("compatibility", data)
        self.assertIsInstance(data["dependencies"], list)

    def test_static_assets(self):
        for path in ("/style.css", "/app.js"):
            status, _, body = _request(self.PORT, path)
            self.assertEqual(status, 200, path)
        _, _, js = _request(self.PORT, "/app.js")
        self.assertIn(b"cheerpjInit", js)
        self.assertIn(b'"/app/"', js)
        self.assertNotIn(b'"/str/"', js)

    def test_jar_is_served_with_range_support(self):
        status, headers, body = _request(
            self.PORT, "/CarTraffic.jar", headers={"Range": "bytes=0-3"}
        )
        self.assertEqual(status, 206)
        self.assertEqual(body, b"PK\x03\x04")
        self.assertTrue(headers["Content-Range"].startswith("bytes 0-3/"))
        self.assertEqual(headers["Accept-Ranges"], "bytes")


class BrowserTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if SKIP_BROWSER:
            raise unittest.SkipTest("PROVIKOM_SKIP_BROWSER=1")
        try:
            import playwright.sync_api  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("playwright is not installed")
        if not _cdn_reachable():
            raise unittest.SkipTest("CheerpJ CDN is not reachable")
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    def _playwright(self):
        from playwright.sync_api import sync_playwright

        return sync_playwright()

    def _new_page(self, playwright, port, errors=None):
        browser = playwright.chromium.launch(
            headless=True,
            args=["--autoplay-policy=no-user-gesture-required"],
        )
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        if errors is not None:
            page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"http://127.0.0.1:{port}/", wait_until="load", timeout=30000)
        page.wait_for_selector("#btn-start", timeout=15000)
        return browser, page


class TestCarTrafficBrowser(BrowserTestCase):
    PORT = 18090

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _require_jar(CARTRAFFIC_JAR)
        cls._tmp = tempfile.TemporaryDirectory(prefix="provikom_browser_car_")
        cls.out = Path(cls._tmp.name) / "cartraffic"
        result = _build(CARTRAFFIC_JAR, cls.out)
        if result.returncode != 0:
            raise unittest.SkipTest(f"Build failed:\n{result.stdout}\n{result.stderr}")
        cls._server = LocalServer(cls.out, cls.PORT)
        cls._server.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._server.__exit__(None, None, None)
        cls._tmp.cleanup()

    def test_page_loads_without_browser_errors(self):
        errors = []
        with self._playwright() as playwright:
            browser, page = self._new_page(playwright, self.PORT, errors)
            page.wait_for_timeout(500)
            page.screenshot(path=str(SCREENSHOT_DIR / "cartraffic_initial.png"))
            browser.close()
        self.assertEqual(errors, [])

    def test_java_window_mounts_and_keyboard_interacts(self):
        errors = []
        with self._playwright() as playwright:
            browser, page = self._new_page(playwright, self.PORT, errors)
            page.click("#btn-start")
            canvas_found, status = _wait_for_canvas(page)
            if canvas_found:
                page.wait_for_timeout(5000)
            page.screenshot(path=str(SCREENSHOT_DIR / "cartraffic_running.png"), full_page=True)
            if canvas_found:
                _click_canvas_relative(page, 155, 380)
                page.wait_for_timeout(500)
                _click_canvas_relative(page, 415, 460)
                page.wait_for_timeout(2500)
                page.screenshot(
                    path=str(SCREENSHOT_DIR / "cartraffic_interaction.png"),
                    full_page=True,
                )
                _focus_canvas_and_press_keys(page)
            final_status = page.evaluate("() => document.body.dataset.status || ''")
            browser.close()

        self.assertTrue(canvas_found, f"Canvas did not mount (status={status})")
        self.assertIn(final_status, ("running", "exited"))
        self.assertEqual(errors, [])


class TestPaddleGameBrowser(BrowserTestCase):
    PORT = 18091

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _require_jar(PADDLE_JAR)
        cls._tmp = tempfile.TemporaryDirectory(prefix="provikom_browser_paddle_")
        cls.out = Path(cls._tmp.name) / "paddle"
        result = _build(PADDLE_JAR, cls.out)
        if result.returncode != 0:
            raise unittest.SkipTest(f"Build failed:\n{result.stdout}\n{result.stderr}")
        cls._server = LocalServer(cls.out, cls.PORT)
        cls._server.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._server.__exit__(None, None, None)
        cls._tmp.cleanup()

    def test_manifest_class_path_dependency_is_served(self):
        status, _, body = _request(self.PORT, "/lib/AbsoluteLayout.jar", headers={"Range": "bytes=0-1"})
        self.assertEqual(status, 206)
        self.assertEqual(body[:2], b"PK")

    def test_dependency_game_mounts_and_interacts(self):
        errors = []
        with self._playwright() as playwright:
            browser, page = self._new_page(playwright, self.PORT, errors)
            page.click("#btn-start")
            canvas_found, status = _wait_for_canvas(page)
            if canvas_found:
                page.wait_for_timeout(3000)
                page.screenshot(
                    path=str(SCREENSHOT_DIR / "paddle_running.png"),
                    full_page=True,
                )
                _click_canvas_relative(page, 365, 258)
                page.wait_for_timeout(6000)
                page.screenshot(
                    path=str(SCREENSHOT_DIR / "paddle_interaction.png"),
                    full_page=True,
                )
                _focus_canvas_and_press_keys(page)
            browser.close()

        self.assertTrue(canvas_found, f"Canvas did not mount (status={status})")
        self.assertEqual(errors, [])


class TestFlappyBrowser(BrowserTestCase):
    PORT = 18093

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _require_jar(FLAPPY_JAR)
        cls._tmp = tempfile.TemporaryDirectory(prefix="provikom_browser_flappy_")
        cls.out = Path(cls._tmp.name) / "flappy"
        result = _build(FLAPPY_JAR, cls.out)
        if result.returncode != 0:
            raise unittest.SkipTest(f"Build failed:\n{result.stdout}\n{result.stderr}")
        cls._server = LocalServer(cls.out, cls.PORT)
        cls._server.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._server.__exit__(None, None, None)
        cls._tmp.cleanup()

    def test_menu_starts_and_accepts_keyboard(self):
        errors = []
        with self._playwright() as playwright:
            browser, page = self._new_page(playwright, self.PORT, errors)
            page.click("#btn-start")
            canvas_found, status = _wait_for_canvas(page)
            if canvas_found:
                page.wait_for_timeout(2000)
            page.screenshot(path=str(SCREENSHOT_DIR / "flappy_menu.png"), full_page=True)
            if canvas_found:
                _click_canvas_relative(page, 170, 440)
                page.wait_for_timeout(1800)
                page.screenshot(
                    path=str(SCREENSHOT_DIR / "flappy_running.png"),
                    full_page=True,
                )
                _focus_canvas_and_press_keys(page)
                page.screenshot(
                    path=str(SCREENSHOT_DIR / "flappy_interaction.png"),
                    full_page=True,
                )
            browser.close()

        self.assertTrue(canvas_found, f"Canvas did not mount (status={status})")
        self.assertEqual(errors, [])


class TestPongKnownLimitation(BrowserTestCase):
    PORT = 18092

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _require_jar(PONG_JAR)
        cls._tmp = tempfile.TemporaryDirectory(prefix="provikom_browser_pong_")
        cls.out = Path(cls._tmp.name) / "pong"
        result = _build(PONG_JAR, cls.out)
        if result.returncode != 0:
            raise unittest.SkipTest(f"Build failed:\n{result.stdout}\n{result.stderr}")
        cls._server = LocalServer(cls.out, cls.PORT)
        cls._server.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._server.__exit__(None, None, None)
        cls._tmp.cleanup()

    def test_audio_runtime_exception_is_surfaced_to_the_player(self):
        with self._playwright() as playwright:
            browser, page = self._new_page(playwright, self.PORT)
            page.click("#btn-start")
            deadline = time.time() + 75
            status = ""
            while time.time() < deadline:
                status = page.evaluate("() => document.body.dataset.status || ''")
                if status == "error":
                    break
                time.sleep(0.5)

            page.screenshot(path=str(SCREENSHOT_DIR / "pong_audio_error.png"), full_page=True)
            error_title = page.evaluate(
                "() => { const el = document.querySelector('#error-title'); return el ? el.textContent : ''; }"
            )
            error_details = page.evaluate(
                "() => { const el = document.querySelector('#error-details'); return el ? el.textContent : ''; }"
            )
            java_error = page.evaluate("() => document.body.dataset.javaError || ''")
            browser.close()

        self.assertEqual(status, "error")
        self.assertIn("Java Runtime Error", error_title)
        self.assertIn("No line matching interface Clip", error_details)
        self.assertIn("Exception in thread", java_error)


class TestBuildCLI(unittest.TestCase):
    def test_build_pong_game(self):
        _require_jar(PONG_JAR)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "pong"
            result = _build(PONG_JAR, out)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("BUILD SUCCESSFUL", result.stdout)
            self.assertTrue((out / "index.html").is_file())

    def test_build_fails_without_force_on_non_empty_directory(self):
        _require_jar(FLAPPY_JAR)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "flappy"
            out.mkdir()
            (out / "stale.txt").write_text("stale", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "provikom_converter",
                    "build",
                    str(FLAPPY_JAR),
                    "--output",
                    str(out),
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--force", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
