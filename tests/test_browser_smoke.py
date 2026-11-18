"""HTTP and Chromium verification for generated CheerpJ web artifacts.

HTTP tests always run. Browser tests require Playwright, Chromium, Pillow, the
pinned game fixtures, and network access to the CheerpJ CDN.

Local usage:
    python -m unittest tests.test_browser_smoke -v
    PROVIKOM_SKIP_BROWSER=1 python -m unittest discover -s tests -v

CI usage (missing dependencies/fixtures/network must fail, not skip):
    PROVIKOM_REQUIRE_FIXTURES=1 PROVIKOM_REQUIRE_BROWSER=1 \
        python -m unittest tests.test_browser_smoke -v
"""

from __future__ import annotations

import http.client
import http.server
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from provikom_converter.lifecycle import (
    apply_verification_to_manifest,
    make_verification_record,
)
from provikom_converter.server import RangeRequestHandler
from tests.fixtures import find_project2024_games_dir, require_fixture

ROOT = Path(__file__).resolve().parent.parent
GAMES_DIR = find_project2024_games_dir()
PONG_JAR = GAMES_DIR / "PongGame.jar"
FLAPPY_JAR = GAMES_DIR / "flappy.jar"
CARTRAFFIC_JAR = GAMES_DIR / "CarTraffic.jar"
PADDLE_JAR = GAMES_DIR / "PaddleGame.jar"
SCREENSHOT_DIR = ROOT / "docs" / "screenshots"
VERIFICATION_DIR = ROOT / "docs" / "verification"
BUILD_VERIFICATION_DIR = ROOT / "build" / "verification"
SKIP_BROWSER = os.environ.get("PROVIKOM_SKIP_BROWSER", "").strip() == "1"
REQUIRE_BROWSER = os.environ.get("PROVIKOM_REQUIRE_BROWSER", "").strip() == "1"
CHEERPJ_LOADER = "https://cjrtnc.leaningtech.com/5.0/loader.js"


def _require_jar(path: Path) -> None:
    require_fixture(path, label="game archive")


def _build_failed(result: subprocess.CompletedProcess) -> None:
    message = f"Build failed:\n{result.stdout}\n{result.stderr}"
    if REQUIRE_BROWSER:
        raise AssertionError(message)
    raise unittest.SkipTest(message)


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
        timeout=240,
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
                with socket.create_connection(
                    ("127.0.0.1", self.server.server_port), timeout=0.25
                ):
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


def _wait_for_canvas(page, timeout=90) -> Tuple[bool, str]:
    deadline = time.time() + timeout
    status = "?"
    while time.time() < deadline:
        status = page.evaluate("() => document.body.dataset.status || ''")
        if page.evaluate(
            """() => [...document.querySelectorAll('#cheerpj-display canvas')].some((c) => {
                const r = c.getBoundingClientRect();
                const style = getComputedStyle(c);
                return r.width > 20 && r.height > 20
                    && style.display !== 'none' && style.visibility !== 'hidden';
            })"""
        ):
            return True, status
        if status == "error":
            return False, status
        time.sleep(0.5)
    return False, status


def _canvas_index(page) -> int:
    return page.evaluate(
        """() => {
            let best = 0;
            let bestArea = -1;
            [...document.querySelectorAll('#cheerpj-display canvas')].forEach((c, index) => {
                const r = c.getBoundingClientRect();
                const style = getComputedStyle(c);
                if (style.display === 'none' || style.visibility === 'hidden') return;
                const area = r.width * r.height;
                if (area > bestArea) { best = index; bestArea = area; }
            });
            return best;
        }"""
    )


def _main_canvas(page):
    return page.locator("#cheerpj-display canvas").nth(_canvas_index(page))


def _focus_canvas_and_press_keys(page):
    box = _canvas_box(page)
    page.mouse.click(box["x"] + box["w"] / 2, box["y"] + box["h"] / 2)
    time.sleep(0.2)
    _main_canvas(page).evaluate("el => { el.tabIndex = 0; el.focus(); }")
    for key in ("Space", "ArrowUp", "ArrowLeft", "ArrowRight"):
        page.keyboard.press(key)
        time.sleep(0.3)


def _canvas_box(page) -> Dict[str, float]:
    return _main_canvas(page).evaluate(
        "el => { const r = el.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; }"
    )


def _click_canvas_relative(page, x: float, y: float) -> None:
    box = _canvas_box(page)
    page.mouse.click(box["x"] + x, box["y"] + y)


def _click_canvas_fraction(page, x: float, y: float) -> None:
    box = _canvas_box(page)
    page.mouse.click(box["x"] + box["w"] * x, box["y"] + box["h"] * y)


def _canvas_bytes(page) -> bytes:
    return _main_canvas(page).screenshot()


def _load_image(data: bytes):
    try:
        from PIL import Image
    except ImportError as exc:
        if REQUIRE_BROWSER:
            raise RuntimeError("Pillow is required for browser verification") from exc
        raise unittest.SkipTest("Pillow is not installed") from exc
    return Image.open(io.BytesIO(data)).convert("RGB")


def _image_stats(data: bytes) -> Dict[str, float]:
    image = _load_image(data)
    sample = image.resize((120, 90))
    raw = sample.tobytes()
    pixels = list(zip(raw[0::3], raw[1::3], raw[2::3]))
    count = len(pixels)
    luminances = [
        0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b in pixels
    ]
    mean = sum(luminances) / count
    variance = sum((value - mean) ** 2 for value in luminances) / count
    unique = len(set(pixels))
    non_dark = sum(1 for r, g, b in pixels if max(r, g, b) > 24) / count

    def ratio(predicate: Callable[[int, int, int], bool]) -> float:
        return sum(1 for pixel in pixels if predicate(*pixel)) / count

    return {
        "unique_colors": float(unique),
        "luminance_stddev": variance ** 0.5,
        "non_dark_ratio": non_dark,
        "purple_ratio": ratio(lambda r, g, b: b > 70 and r > 35 and b > r * 1.25 and r > g),
        "sky_blue_ratio": ratio(lambda r, g, b: b > 150 and g > 120 and b > r * 1.4),
        "warm_ratio": ratio(lambda r, g, b: r > 110 and r > b * 1.3 and g > 30),
    }


def _assert_rendered(
    stats: Dict[str, float],
    label: str,
    *,
    min_unique: float = 45,
    min_stddev: float = 8,
    min_non_dark: float = 0.03,
) -> None:
    if stats["unique_colors"] < min_unique:
        raise AssertionError(
            f"{label}: canvas looks blank (unique_colors={stats['unique_colors']:.0f})"
        )
    if stats["luminance_stddev"] < min_stddev:
        raise AssertionError(
            f"{label}: canvas has too little visual variance "
            f"(luminance_stddev={stats['luminance_stddev']:.2f})"
        )
    if stats["non_dark_ratio"] < min_non_dark:
        raise AssertionError(
            f"{label}: canvas is almost entirely dark "
            f"(non_dark_ratio={stats['non_dark_ratio']:.3f})"
        )


def _difference_ratio(before: bytes, after: bytes) -> float:
    first = _load_image(before).resize((120, 90))
    second = _load_image(after).resize((120, 90))
    first_raw = first.tobytes()
    second_raw = second.tobytes()
    first_pixels = list(zip(first_raw[0::3], first_raw[1::3], first_raw[2::3]))
    second_pixels = list(zip(second_raw[0::3], second_raw[1::3], second_raw[2::3]))
    changed = 0
    for a, b in zip(first_pixels, second_pixels):
        if max(abs(a[0] - b[0]), abs(a[1] - b[1]), abs(a[2] - b[2])) > 18:
            changed += 1
    return changed / len(first_pixels)


def _assert_changed(before: bytes, after: bytes, label: str, minimum: float = 0.02) -> float:
    ratio = _difference_ratio(before, after)
    if ratio < minimum:
        raise AssertionError(
            f"{label}: expected a visible interaction change, got diff ratio {ratio:.4f}"
        )
    return ratio


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _write_verification(name: str, record: Dict) -> Path:
    VERIFICATION_DIR.mkdir(parents=True, exist_ok=True)
    path = VERIFICATION_DIR / f"{name}.json"
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return path


def _fatal_diagnostics(console_messages: List[str]) -> List[str]:
    patterns = (
        "ExceptionInInitializerError",
        "NoClassDefFoundError",
        "UnsatisfiedLinkError",
        "No line matching interface",
        "Exception in thread",
    )
    return [line for line in console_messages if any(p in line for p in patterns)]


class TestArtifactHTTP(unittest.TestCase):
    PORT = 18080

    @classmethod
    def setUpClass(cls):
        _require_jar(CARTRAFFIC_JAR)
        cls._tmp = tempfile.TemporaryDirectory(prefix="provikom_http_")
        cls.out = Path(cls._tmp.name) / "cartraffic"
        result = _build(CARTRAFFIC_JAR, cls.out)
        if result.returncode != 0:
            _build_failed(result)
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
        self.assertEqual(data["schema_version"], "1.1")
        self.assertEqual(data["backend"], "cheerpj")
        self.assertEqual(data["runtime_version"], 25)
        self.assertTrue(data["is_experimental"])
        self.assertEqual(data["entry_point"], "index.html")
        self.assertEqual(data["jar_file"], "CarTraffic.jar")
        self.assertEqual(data["java_major_version"], 66)
        self.assertEqual(data["lifecycle"]["state"], "built")
        self.assertTrue(data["lifecycle"]["prediction_only"])
        self.assertFalse(data["lifecycle"]["execution_verified"])
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
            message = "PROVIKOM_SKIP_BROWSER=1"
            if REQUIRE_BROWSER:
                raise RuntimeError(f"Browser verification is required but {message}")
            raise unittest.SkipTest(message)
        try:
            import playwright.sync_api  # noqa: F401
            import PIL  # noqa: F401
        except ImportError as exc:
            if REQUIRE_BROWSER:
                raise RuntimeError(
                    "Browser verification is required but playwright/Pillow is not installed"
                ) from exc
            raise unittest.SkipTest("playwright or Pillow is not installed")
        if not _cdn_reachable():
            if REQUIRE_BROWSER:
                raise RuntimeError(
                    "Browser verification is required but the CheerpJ CDN is unreachable"
                )
            raise unittest.SkipTest("CheerpJ CDN is not reachable")
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        VERIFICATION_DIR.mkdir(parents=True, exist_ok=True)

    def _playwright(self):
        from playwright.sync_api import sync_playwright

        return sync_playwright()

    def _new_page(
        self,
        playwright,
        port,
        errors: Optional[List[str]] = None,
        console: Optional[List[str]] = None,
    ):
        browser = playwright.chromium.launch(
            headless=True,
            args=["--autoplay-policy=no-user-gesture-required"],
        )
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        if errors is not None:
            page.on("pageerror", lambda error: errors.append(str(error)))
        if console is not None:
            page.on(
                "console",
                lambda message: console.append(f"{message.type}: {message.text}"),
            )
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
            _build_failed(result)
        cls._server = LocalServer(cls.out, cls.PORT)
        cls._server.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._server.__exit__(None, None, None)
        cls._tmp.cleanup()

    def test_page_loads_without_browser_errors(self):
        errors: List[str] = []
        with self._playwright() as playwright:
            browser, page = self._new_page(playwright, self.PORT, errors)
            page.wait_for_timeout(500)
            page.screenshot(path=str(SCREENSHOT_DIR / "cartraffic_initial.png"))
            browser.close()
        self.assertEqual(errors, [])

    def test_menu_renders_and_character_selection_changes_ui(self):
        errors: List[str] = []
        console: List[str] = []
        checks: List[Dict] = []
        started = time.time()
        with self._playwright() as playwright:
            browser, page = self._new_page(playwright, self.PORT, errors, console)
            page.click("#btn-start")
            canvas_found, status = _wait_for_canvas(page)
            checks.append({"name": "canvas_mounted", "passed": canvas_found, "detail": status})
            if not canvas_found:
                page.screenshot(path=str(SCREENSHOT_DIR / "cartraffic_running.png"), full_page=True)
                browser.close()
                self.fail(f"CarTraffic canvas did not mount (status={status})")

            page.wait_for_timeout(5000)
            menu_bytes = _canvas_bytes(page)
            page.screenshot(path=str(SCREENSHOT_DIR / "cartraffic_running.png"), full_page=True)
            menu_stats = _image_stats(menu_bytes)
            _assert_rendered(menu_stats, "CarTraffic menu")
            if menu_stats["purple_ratio"] < 0.08:
                raise AssertionError(
                    f"CarTraffic menu lacks expected purple UI (purple_ratio={menu_stats['purple_ratio']:.3f})"
                )
            checks.append(
                {
                    "name": "menu_ui_rendered",
                    "passed": True,
                    "detail": menu_stats,
                }
            )

            _click_canvas_relative(page, 155, 380)
            page.wait_for_timeout(500)
            _click_canvas_relative(page, 415, 460)
            page.wait_for_timeout(2500)
            theme_bytes = _canvas_bytes(page)
            page.screenshot(
                path=str(SCREENSHOT_DIR / "cartraffic_interaction.png"), full_page=True
            )
            theme_stats = _image_stats(theme_bytes)
            _assert_rendered(theme_stats, "CarTraffic theme page")
            interaction_ratio = _assert_changed(
                menu_bytes, theme_bytes, "CarTraffic character/NEXT interaction", 0.04
            )
            checks.append(
                {
                    "name": "character_selection_and_next",
                    "passed": True,
                    "detail": {"difference_ratio": interaction_ratio, **theme_stats},
                }
            )

            _focus_canvas_and_press_keys(page)
            final_status = page.evaluate("() => document.body.dataset.status || ''")
            browser.close()

        self.assertIn(final_status, ("running", "exited"))
        self.assertEqual(errors, [])
        fatal = _fatal_diagnostics(console)
        self.assertEqual(fatal, [])
        record = make_verification_record(
            game="CarTraffic.jar",
            artifact=_relative(self.out),
            state="runtime_verified",
            checks=checks,
            screenshots=[
                "docs/screenshots/cartraffic_running.png",
                "docs/screenshots/cartraffic_interaction.png",
            ],
            console_errors=errors,
            runtime_diagnostics=console,
            notes=["Automated Chromium verification; manual gameplay verification not performed."],
            duration_seconds=time.time() - started,
        )
        _write_verification("cartraffic", record)
        apply_verification_to_manifest(self.out, record)


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
            _build_failed(result)
        cls._server = LocalServer(cls.out, cls.PORT)
        cls._server.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._server.__exit__(None, None, None)
        cls._tmp.cleanup()

    def test_manifest_class_path_dependency_is_served(self):
        status, _, body = _request(
            self.PORT, "/lib/AbsoluteLayout.jar", headers={"Range": "bytes=0-1"}
        )
        self.assertEqual(status, 206)
        self.assertEqual(body[:2], b"PK")

    def test_level_select_and_easy_mode_render_game_ui(self):
        errors: List[str] = []
        console: List[str] = []
        checks: List[Dict] = []
        started = time.time()
        with self._playwright() as playwright:
            browser, page = self._new_page(playwright, self.PORT, errors, console)
            page.click("#btn-start")
            canvas_found, status = _wait_for_canvas(page)
            checks.append({"name": "canvas_mounted", "passed": canvas_found, "detail": status})
            if not canvas_found:
                page.screenshot(path=str(SCREENSHOT_DIR / "paddle_running.png"), full_page=True)
                browser.close()
                self.fail(f"PaddleGame canvas did not mount (status={status})")

            page.wait_for_timeout(3000)
            menu_bytes = _canvas_bytes(page)
            page.screenshot(path=str(SCREENSHOT_DIR / "paddle_running.png"), full_page=True)
            menu_stats = _image_stats(menu_bytes)
            _assert_rendered(
                menu_stats,
                "Paddle level select",
                min_unique=150,
                min_stddev=18,
                min_non_dark=0.25,
            )
            checks.append({"name": "level_select_rendered", "passed": True, "detail": menu_stats})

            _click_canvas_relative(page, 365, 258)
            page.wait_for_timeout(6500)
            game_bytes = _canvas_bytes(page)
            page.screenshot(
                path=str(SCREENSHOT_DIR / "paddle_interaction.png"), full_page=True
            )
            game_stats = _image_stats(game_bytes)
            _assert_rendered(
                game_stats,
                "Paddle easy mode",
                min_unique=120,
                min_stddev=12,
                min_non_dark=0.10,
            )
            interaction_ratio = _assert_changed(
                menu_bytes, game_bytes, "Paddle Easy mode interaction", 0.05
            )
            checks.append(
                {
                    "name": "easy_mode_started_game_ui",
                    "passed": True,
                    "detail": {"difference_ratio": interaction_ratio, **game_stats},
                }
            )

            _focus_canvas_and_press_keys(page)
            final_status = page.evaluate("() => document.body.dataset.status || ''")
            browser.close()

        self.assertIn(final_status, ("running", "exited"))
        self.assertEqual(errors, [])
        fatal = _fatal_diagnostics(console)
        self.assertEqual(fatal, [])
        self.assertTrue(
            any("mark/reset not supported" in line for line in console),
            "Expected PaddleGame's known non-fatal audio diagnostic to be captured",
        )
        record = make_verification_record(
            game="PaddleGame.jar",
            artifact=_relative(self.out),
            state="runtime_verified",
            checks=checks,
            screenshots=[
                "docs/screenshots/paddle_running.png",
                "docs/screenshots/paddle_interaction.png",
            ],
            console_errors=errors,
            runtime_diagnostics=console,
            notes=[
                "Automated Chromium verification; manual gameplay verification not performed.",
                "Known non-fatal audio diagnostic: java.io.IOException: mark/reset not supported.",
            ],
            duration_seconds=time.time() - started,
        )
        _write_verification("paddle-game", record)
        apply_verification_to_manifest(self.out, record)


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
            _build_failed(result)
        cls._server = LocalServer(cls.out, cls.PORT)
        cls._server.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._server.__exit__(None, None, None)
        cls._tmp.cleanup()

    def test_menu_and_gameplay_render_with_input(self):
        errors: List[str] = []
        console: List[str] = []
        checks: List[Dict] = []
        started = time.time()
        with self._playwright() as playwright:
            browser, page = self._new_page(playwright, self.PORT, errors, console)
            page.click("#btn-start")
            canvas_found, status = _wait_for_canvas(page)
            checks.append({"name": "canvas_mounted", "passed": canvas_found, "detail": status})
            if not canvas_found:
                page.screenshot(path=str(SCREENSHOT_DIR / "flappy_menu.png"), full_page=True)
                browser.close()
                self.fail(f"Flappy canvas did not mount (status={status})")

            page.wait_for_timeout(2000)
            menu_bytes = _canvas_bytes(page)
            page.screenshot(path=str(SCREENSHOT_DIR / "flappy_menu.png"), full_page=True)
            menu_stats = _image_stats(menu_bytes)
            _assert_rendered(
                menu_stats,
                "Flappy menu",
                min_unique=20,
                min_stddev=3,
                min_non_dark=0.05,
            )
            if menu_stats["sky_blue_ratio"] < 0.25:
                raise AssertionError(
                    f"Flappy menu lacks expected sky UI (sky_blue_ratio={menu_stats['sky_blue_ratio']:.3f})"
                )
            checks.append({"name": "menu_rendered", "passed": True, "detail": menu_stats})

            _click_canvas_relative(page, 170, 440)
            page.wait_for_timeout(2000)
            running_bytes = _canvas_bytes(page)
            page.screenshot(path=str(SCREENSHOT_DIR / "flappy_running.png"), full_page=True)
            running_stats = _image_stats(running_bytes)
            _assert_rendered(
                running_stats,
                "Flappy gameplay",
                min_unique=20,
                min_stddev=3,
                min_non_dark=0.05,
            )
            play_ratio = _assert_changed(
                menu_bytes, running_bytes, "Flappy PLAY interaction", 0.02
            )
            checks.append(
                {
                    "name": "play_started_gameplay",
                    "passed": True,
                    "detail": {"difference_ratio": play_ratio, **running_stats},
                }
            )

            _focus_canvas_and_press_keys(page)
            page.wait_for_timeout(1000)
            interaction_bytes = _canvas_bytes(page)
            page.screenshot(
                path=str(SCREENSHOT_DIR / "flappy_interaction.png"), full_page=True
            )
            interaction_stats = _image_stats(interaction_bytes)
            _assert_rendered(
                interaction_stats,
                "Flappy after keyboard input",
                min_unique=20,
                min_stddev=3,
                min_non_dark=0.05,
            )
            input_ratio = _difference_ratio(running_bytes, interaction_bytes)
            checks.append(
                {
                    "name": "keyboard_input_dispatched",
                    "passed": True,
                    "detail": {
                        "visual_change_ratio": input_ratio,
                        "note": "Keyboard events were sent after canvas focus; PLAY click is the asserted input interaction.",
                        **interaction_stats,
                    },
                }
            )

            final_status = page.evaluate("() => document.body.dataset.status || ''")
            browser.close()

        self.assertIn(final_status, ("running", "exited"))
        self.assertEqual(errors, [])
        fatal = _fatal_diagnostics(console)
        self.assertEqual(fatal, [])
        record = make_verification_record(
            game="flappy.jar",
            artifact=_relative(self.out),
            state="runtime_verified",
            checks=checks,
            screenshots=[
                "docs/screenshots/flappy_menu.png",
                "docs/screenshots/flappy_running.png",
                "docs/screenshots/flappy_interaction.png",
            ],
            console_errors=errors,
            runtime_diagnostics=console,
            notes=["Automated Chromium verification; manual gameplay verification not performed."],
            duration_seconds=time.time() - started,
        )
        _write_verification("flappy", record)
        apply_verification_to_manifest(self.out, record)


class TestPongKnownLimitation(BrowserTestCase):
    PORT = 18092

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _require_jar(PONG_JAR)
        cls._tmp = tempfile.TemporaryDirectory(prefix="provikom_browser_pong_")
        cls.out = BUILD_VERIFICATION_DIR / "pong"
        result = _build(PONG_JAR, cls.out)
        if result.returncode != 0:
            _build_failed(result)
        cls._server = LocalServer(cls.out, cls.PORT)
        cls._server.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._server.__exit__(None, None, None)
        cls._tmp.cleanup()

    def test_audio_runtime_exception_is_surfaced_and_artifact_preserved(self):
        errors: List[str] = []
        console: List[str] = []
        checks: List[Dict] = []
        started = time.time()
        with self._playwright() as playwright:
            browser, page = self._new_page(playwright, self.PORT, errors, console)
            page.click("#btn-start")
            deadline = time.time() + 90
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

        checks.append(
            {
                "name": "java_runtime_error_surfaced",
                "passed": status == "error",
                "detail": {"status": status, "title": error_title},
            }
        )
        self.assertEqual(status, "error")
        self.assertIn("Java Runtime Error", error_title)
        self.assertIn("No line matching interface Clip", error_details)
        self.assertIn("Exception in thread", java_error)
        self.assertTrue((self.out / "index.html").is_file())
        self.assertTrue((self.out / "manifest.json").is_file())
        self.assertTrue(
            any("No line matching interface Clip" in line for line in console),
            "Expected the Pong Clip exception in captured console diagnostics",
        )

        record = make_verification_record(
            game="PongGame.jar",
            artifact=_relative(self.out),
            state="failed",
            checks=checks,
            screenshots=["docs/screenshots/pong_audio_error.png"],
            console_errors=errors,
            runtime_diagnostics=console,
            notes=[
                "Known limitation: browser Clip support rejects the game's 8-bit mono 44.1 kHz WAV.",
                "Artifact intentionally retained under build/verification/pong for debugging.",
                "Automated Chromium verification; manual gameplay verification not performed.",
            ],
            duration_seconds=time.time() - started,
        )
        _write_verification("pong-game", record)
        manifest = apply_verification_to_manifest(self.out, record)
        self.assertEqual(manifest["lifecycle"]["state"], "failed")
        self.assertFalse(manifest["lifecycle"]["execution_verified"])
        self.assertEqual(manifest["compatibility"]["status"], "supported_with_workarounds")


class TestBuildCLI(unittest.TestCase):
    def test_build_pong_game(self):
        _require_jar(PONG_JAR)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "pong"
            result = _build(PONG_JAR, out)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("BUILD SUCCESSFUL", result.stdout)
            self.assertTrue((out / "index.html").is_file())
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["lifecycle"]["state"], "built")

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
