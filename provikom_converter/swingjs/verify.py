"""Generic Chromium verification for source-backed SwingJS artifacts."""

from __future__ import annotations

import functools
import http.server
import io
import json
import re
import socketserver
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from provikom_converter.build_safety import refresh_ownership_marker
from provikom_converter.lifecycle import (
    apply_verification_to_manifest,
    make_verification_record,
)

STATE_RE = re.compile(
    r"STATE x=(-?\d+) y=(-?\d+) dx=(-?\d+) dy=(-?\d+) paused=(true|false) ticks=(\d+)"
)
FIXTURE_RE = re.compile(
    r"FIXTURE ticks=(\d+) clicks=(\d+) phase=(-?[\d.]+) running=(true|false)"
)


class SwingJSVerifyError(RuntimeError):
    pass


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass


class _LocalServer:
    def __init__(self, directory: Path):
        socketserver.ThreadingTCPServer.allow_reuse_address = True
        self.server = socketserver.ThreadingTCPServer(
            ("127.0.0.1", 0),
            functools.partial(_QuietHandler, directory=str(directory)),
        )
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.server.shutdown()
        self.server.server_close()


def _states(text: str) -> List[Dict[str, object]]:
    return [
        {
            "x": int(x),
            "y": int(y),
            "dx": int(dx),
            "dy": int(dy),
            "paused": paused == "true",
            "ticks": int(ticks),
        }
        for x, y, dx, dy, paused, ticks in STATE_RE.findall(text)
    ]


def _fixture_states(text: str) -> List[Dict[str, object]]:
    return [
        {
            "ticks": int(ticks),
            "clicks": int(clicks),
            "phase": float(phase),
            "running": running == "true",
        }
        for ticks, clicks, phase, running in FIXTURE_RE.findall(text)
    ]


def _wait_for_fixture(
    page,
    predicate: Callable[[Dict[str, object]], bool],
    label: str,
    timeout: float = 10.0,
) -> Dict[str, object]:
    deadline = time.time() + timeout
    last: Optional[Dict[str, object]] = None
    while time.time() < deadline:
        states = _fixture_states(page.locator("#sysoutdiv").inner_text())
        if states:
            last = states[-1]
            if predicate(last):
                return last
        page.wait_for_timeout(100)
    raise SwingJSVerifyError("Timed out waiting for {} (last fixture state: {})".format(label, last))


def _wait_for_state(
    page,
    predicate: Callable[[Dict[str, object]], bool],
    label: str,
    timeout: float = 10.0,
) -> Dict[str, object]:
    deadline = time.time() + timeout
    last: Optional[Dict[str, object]] = None
    while time.time() < deadline:
        states = _states(page.locator("#sysoutdiv").inner_text())
        if states:
            last = states[-1]
            if predicate(last):
                return last
        page.wait_for_timeout(100)
    raise SwingJSVerifyError("Timed out waiting for {} (last state: {})".format(label, last))


def _image_stats(data: bytes) -> Dict[str, float]:
    from PIL import Image

    image = Image.open(io.BytesIO(data)).convert("RGB")
    sample = image.resize((120, 90))
    raw = sample.tobytes()
    pixels = list(zip(raw[0::3], raw[1::3], raw[2::3]))
    count = len(pixels)
    luminances = [0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b in pixels]
    mean = sum(luminances) / count
    variance = sum((value - mean) ** 2 for value in luminances) / count
    return {
        "unique_colors": float(len(set(pixels))),
        "luminance_stddev": variance ** 0.5,
        "non_dark_ratio": sum(1 for pixel in pixels if max(pixel) > 24) / count,
    }


def _require_pixels(stats: Dict[str, float]) -> None:
    if stats["unique_colors"] < 20:
        raise SwingJSVerifyError("Canvas appears blank ({} unique colors)".format(stats["unique_colors"]))
    if stats["luminance_stddev"] < 5:
        raise SwingJSVerifyError(
            "Canvas has too little visual variance ({:.2f})".format(stats["luminance_stddev"])
        )
    if stats["non_dark_ratio"] < 0.05:
        raise SwingJSVerifyError(
            "Canvas is almost entirely dark ({:.3f})".format(stats["non_dark_ratio"])
        )


def verify_artifact(
    artifact_dir: Path,
    *,
    evidence: Optional[Path] = None,
    screenshot: Optional[Path] = None,
) -> Dict[str, object]:
    """Load a built artifact in headless Chromium and write runtime evidence."""
    artifact = Path(artifact_dir).expanduser().resolve()
    try:
        artifact_label = artifact.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        artifact_label = str(artifact)
    index = artifact / "index.html"
    manifest_path = artifact / "manifest.json"
    if not index.is_file() or not manifest_path.is_file():
        raise SwingJSVerifyError(
            "Artifact is incomplete: expected index.html and manifest.json under {}".format(artifact)
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SwingJSVerifyError("Artifact manifest is not valid JSON: {}".format(exc)) from exc
    source = manifest.get("source_project") if isinstance(manifest.get("source_project"), dict) else {}
    game_title = str(manifest.get("game", {}).get("title") or artifact.name)
    generated_js_rel = str(source.get("generated_js") or "")
    if not generated_js_rel:
        raise SwingJSVerifyError("Manifest is missing source_project.generated_js")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SwingJSVerifyError(
            "Playwright is required. Install with: pip install -e '.[browser]'"
        ) from exc
    try:
        import PIL  # noqa: F401
    except ImportError as exc:
        raise SwingJSVerifyError(
            "Pillow is required. Install with: pip install -e '.[browser]'"
        ) from exc

    errors: List[str] = []
    console: List[str] = []
    failed: List[str] = []
    http_errors: List[Tuple[int, str]] = []
    checks: List[Dict[str, object]] = []
    network_bytes = 0
    network_requests = 0
    generated_js_seen = False
    started = time.time()

    def on_loading_finished(params):
        nonlocal network_bytes
        network_bytes += int(params.get("encodedDataLength") or 0)

    def on_request(params):
        nonlocal network_requests
        network_requests += 1

    screenshot_path = artifact / "verification.png"
    requested_screenshot = (
        Path(screenshot).expanduser().resolve() if screenshot else None
    )
    with _LocalServer(artifact) as server:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            cdp = context.new_cdp_session(page)
            cdp.on("Network.loadingFinished", on_loading_finished)
            cdp.on("Network.requestWillBeSent", on_request)
            cdp.send("Network.enable")
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "console",
                lambda message: console.append("{}: {}".format(message.type, message.text)),
            )
            page.on(
                "requestfailed",
                lambda request: failed.append(
                    "{} :: {}".format(request.url, request.failure)
                ),
            )

            def on_response(response):
                nonlocal generated_js_seen
                try:
                    if response.status >= 400:
                        http_errors.append((response.status, response.url))
                    if response.url.endswith("/" + generated_js_rel) and response.status == 200:
                        generated_js_seen = True
                except Exception:
                    pass

            page.on("response", on_response)
            page.goto(
                "http://127.0.0.1:{}/index.html".format(server.port),
                wait_until="load",
                timeout=60000,
            )
            page.wait_for_selector("canvas", timeout=60000)
            canvas = page.locator("canvas").first
            canvas.wait_for(state="visible", timeout=60000)
            startup_ms = (time.time() - started) * 1000
            box = canvas.bounding_box()
            if not box or box["width"] < 200 or box["height"] < 200:
                raise SwingJSVerifyError("Canvas has an unexpected size: {}".format(box))
            checks.append(
                {
                    "name": "canvas_mounted",
                    "passed": True,
                    "detail": {
                        "width": round(box["width"]),
                        "height": round(box["height"]),
                        "startup_ms": round(startup_ms, 1),
                    },
                }
            )

            page.wait_for_timeout(1000)
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)
            canvas_bytes = canvas.screenshot()
            stats = _image_stats(canvas_bytes)
            _require_pixels(stats)
            checks.append(
                {"name": "graphics_rendered", "passed": True, "detail": stats}
            )
            checks.append(
                {
                    "name": "generated_javascript_loaded",
                    "passed": generated_js_seen,
                    "detail": generated_js_rel,
                }
            )
            if not generated_js_seen:
                raise SwingJSVerifyError(
                    "Browser did not load generated JavaScript: {}".format(generated_js_rel)
                )

            sysout_available = page.locator("#sysoutdiv").count() > 0
            has_state = bool(_states(page.locator("#sysoutdiv").inner_text())) if sysout_available else False
            has_fixture_state = (
                bool(_fixture_states(page.locator("#sysoutdiv").inner_text()))
                if sysout_available
                else False
            )
            if has_state:
                initial = _wait_for_state(page, lambda state: state["ticks"] > 0, "first timer tick")
                page.wait_for_timeout(700)
                moving = _wait_for_state(
                    page,
                    lambda state: state["ticks"] > initial["ticks"],
                    "timer advancement",
                )
                checks.append(
                    {
                        "name": "swing_timer_animates",
                        "passed": True,
                        "detail": {"ticks": moving["ticks"]},
                    }
                )
                box = canvas.bounding_box()
                page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                page.wait_for_timeout(300)
                before = _states(page.locator("#sysoutdiv").inner_text())[-1]
                horizontal = "ArrowLeft" if before["dx"] > 0 else "ArrowRight"
                vertical = "ArrowUp" if before["dy"] > 0 else "ArrowDown"
                page.keyboard.press(horizontal)
                left = _wait_for_state(
                    page,
                    lambda state: (state["dx"] < 0) if horizontal == "ArrowLeft" else (state["dx"] > 0),
                    "horizontal arrow direction",
                )
                checks.append(
                    {
                        "name": "keyboard_horizontal",
                        "passed": True,
                        "detail": {"key": horizontal, "dx": left["dx"]},
                    }
                )
                page.keyboard.press(vertical)
                up = _wait_for_state(
                    page,
                    lambda state: (state["dy"] < 0) if vertical == "ArrowUp" else (state["dy"] > 0),
                    "vertical arrow direction",
                )
                checks.append(
                    {
                        "name": "keyboard_vertical",
                        "passed": True,
                        "detail": {"key": vertical, "dy": up["dy"]},
                    }
                )
                page.keyboard.press("Space")
                paused = _wait_for_state(page, lambda state: state["paused"], "space pause")
                page.wait_for_timeout(500)
                paused_later = _states(page.locator("#sysoutdiv").inner_text())[-1]
                if not paused_later["paused"] or paused_later["ticks"] != paused["ticks"]:
                    raise SwingJSVerifyError(
                        "Pause did not persist: {} -> {}".format(paused, paused_later)
                    )
                checks.append(
                    {
                        "name": "keyboard_pause",
                        "passed": True,
                        "detail": {"ticks": paused["ticks"]},
                    }
                )
                page.keyboard.press("Space")
                _wait_for_state(page, lambda state: not state["paused"], "space unpause")
                page.keyboard.press("KeyR")
                deadline = time.time() + 8
                while time.time() < deadline:
                    states = _states(page.locator("#sysoutdiv").inner_text())
                    if any(
                        state["ticks"] == 0
                        and state["x"] == 80
                        and state["y"] == 200
                        and not state["paused"]
                        for state in states
                    ):
                        break
                    page.wait_for_timeout(100)
                else:
                    raise SwingJSVerifyError("Reset key did not produce the initial state")
                checks.append(
                    {"name": "keyboard_reset", "passed": True, "detail": {"states": len(states)}}
                )
            elif has_fixture_state:
                initial_fixture = _wait_for_fixture(
                    page, lambda state: state["ticks"] > 0, "first fixture timer tick"
                )
                page.wait_for_timeout(700)
                moving_fixture = _wait_for_fixture(
                    page,
                    lambda state: state["ticks"] > initial_fixture["ticks"],
                    "fixture timer advancement",
                )
                checks.append(
                    {
                        "name": "swing_timer_animates",
                        "passed": True,
                        "detail": {"ticks": moving_fixture["ticks"]},
                    }
                )
                box = canvas.bounding_box()
                before_click = _fixture_states(page.locator("#sysoutdiv").inner_text())[-1]
                page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                after_click = _wait_for_fixture(
                    page,
                    lambda state: state["clicks"] > before_click["clicks"],
                    "fixture mouse click",
                )
                checks.append(
                    {
                        "name": "mouse_click_responds",
                        "passed": True,
                        "detail": {"clicks": after_click["clicks"]},
                    }
                )

            memory = page.evaluate(
                """() => performance.memory ? {
                    usedJSHeapSize: performance.memory.usedJSHeapSize,
                    totalJSHeapSize: performance.memory.totalJSHeapSize,
                    jsHeapSizeLimit: performance.memory.jsHeapSizeLimit
                } : null"""
            )
            page.wait_for_timeout(200)
            body_text = page.locator("body").inner_text()
            warnings = []
            if any(status == 404 and url.endswith("/swingjs/j2s/core/package.js") for status, url in http_errors):
                warnings.append(
                    "SwingJS requested an absent core/package.js; this is a non-fatal loader warning."
                )
            browser.close()

    unexpected_http = [
        entry
        for entry in http_errors
        if not (entry[0] == 404 and entry[1].endswith("/swingjs/j2s/core/package.js"))
    ]
    if unexpected_http:
        raise SwingJSVerifyError("Unexpected HTTP errors: {}".format(unexpected_http))
    fatal = [
        line
        for line in console
        if (line.startswith("error:") and "Failed to load resource" not in line)
        or "Exception in thread" in line
        or "NoClassDefFoundError" in line
    ]
    if errors:
        raise SwingJSVerifyError("Browser page errors: {}".format(errors))
    if failed:
        raise SwingJSVerifyError("Failed network requests: {}".format(failed))
    if fatal:
        raise SwingJSVerifyError("Fatal browser console messages: {}".format(fatal))

    record = make_verification_record(
        game=game_title,
        artifact=artifact_label,
        state="runtime_verified",
        checks=checks,
        screenshots=["verification.png"],
        console_errors=[],
        runtime_diagnostics=[],
        notes=warnings,
        automated=True,
        duration_seconds=(time.time() - started),
    )
    record["source_sha256"] = source.get("source_sha256")
    record["generated_js_sha256"] = source.get("generated_js_sha256")
    record["metrics"] = {
        "startup_ms": round(startup_ms, 1),
        "network_bytes": network_bytes,
        "network_requests": network_requests,
        "memory": memory,
    }
    record["http_errors"] = [{"status": status, "url": url} for status, url in http_errors]
    record["console_tail"] = console[-30:]
    record["body_text_tail"] = body_text[-1000:]
    apply_verification_to_manifest(artifact, record)
    manifest_path = artifact / "manifest.json"
    updated = json.loads(manifest_path.read_text(encoding="utf-8"))
    generated = updated.setdefault("generated_files", [])
    if "verification.png" not in generated:
        generated.append("verification.png")
        manifest_path.write_text(json.dumps(updated, indent=2), encoding="utf-8")
        refresh_ownership_marker(artifact)
    if requested_screenshot is not None and requested_screenshot != screenshot_path:
        requested_screenshot.parent.mkdir(parents=True, exist_ok=True)
        requested_screenshot.write_bytes(screenshot_path.read_bytes())
    if evidence is not None:
        evidence_path = Path(evidence).expanduser().resolve()
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record
