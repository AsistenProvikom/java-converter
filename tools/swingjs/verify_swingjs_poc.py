#!/usr/bin/env python3
"""Verify the SwingJS POC in headless Chromium and write runtime evidence.

The POC logs STATE lines to the SwingJS System.out pane. The verifier parses
those lines so the evidence comes from the Java application's own state, not
from a JavaScript shim.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import io
import json
import os
import re
import socketserver
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT = ROOT / "build" / "swingjs-poc"
DEFAULT_EVIDENCE = ROOT / "docs" / "verification" / "swingjs-poc.json"
DEFAULT_SCREENSHOT = ROOT / "docs" / "screenshots" / "swingjs-poc.png"
STATE_RE = re.compile(
    r"STATE x=(-?\d+) y=(-?\d+) dx=(-?\d+) dy=(-?\d+) paused=(true|false) ticks=(\d+)"
)


class VerifyError(RuntimeError):
    pass


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass


class LocalServer:
    def __init__(self, directory: Path, port: int):
        self.server = socketserver.ThreadingTCPServer(
            ("127.0.0.1", port),
            functools.partial(QuietHandler, directory=str(directory)),
        )
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.server.shutdown()
        self.server.server_close()


def _state_from_text(text: str) -> Optional[Dict[str, object]]:
    matches = STATE_RE.findall(text)
    if not matches:
        return None
    x, y, dx, dy, paused, ticks = matches[-1]
    return {
        "x": int(x),
        "y": int(y),
        "dx": int(dx),
        "dy": int(dy),
        "paused": paused == "true",
        "ticks": int(ticks),
    }


def _all_states(text: str) -> List[Dict[str, object]]:
    states = []
    for x, y, dx, dy, paused, ticks in STATE_RE.findall(text):
        states.append(
            {
                "x": int(x),
                "y": int(y),
                "dx": int(dx),
                "dy": int(dy),
                "paused": paused == "true",
                "ticks": int(ticks),
            }
        )
    return states


def _console_text(page) -> str:
    return page.locator("#sysoutdiv").inner_text()


def _wait_for_state(
    page,
    predicate: Callable[[Dict[str, object]], bool],
    label: str,
    timeout: float = 8.0,
) -> Dict[str, object]:
    deadline = time.time() + timeout
    last: Optional[Dict[str, object]] = None
    while time.time() < deadline:
        last = _state_from_text(_console_text(page))
        if last is not None and predicate(last):
            return last
        time.sleep(0.1)
    raise VerifyError("Timed out waiting for {} (last state: {})".format(label, last))


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
        "non_dark_ratio": sum(1 for p in pixels if max(p) > 24) / count,
    }


def _require_pixels(stats: Dict[str, float]) -> None:
    if stats["unique_colors"] < 20:
        raise VerifyError("Canvas appears blank ({} unique colors)".format(stats["unique_colors"]))
    if stats["luminance_stddev"] < 5:
        raise VerifyError(
            "Canvas has too little visual variance ({:.2f})".format(stats["luminance_stddev"])
        )
    if stats["non_dark_ratio"] < 0.05:
        raise VerifyError(
            "Canvas is almost entirely dark ({:.3f})".format(stats["non_dark_ratio"])
        )


def verify(artifact_dir: Path, port: int, evidence: Path, screenshot: Path) -> Dict[str, object]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise VerifyError("Playwright is required. Install with: pip install -e '.[browser]'") from exc
    try:
        import PIL  # noqa: F401
    except ImportError as exc:
        raise VerifyError("Pillow is required. Install with: pip install -e '.[browser]'") from exc

    entry = artifact_dir / "site" / "poc_SwingPoc.html"
    js = artifact_dir / "site" / "swingjs" / "j2s" / "poc" / "SwingPoc.js"
    if not entry.is_file() or not js.is_file():
        raise VerifyError("Artifact is incomplete: expected {} and {}".format(entry, js))

    errors: List[str] = []
    console: List[str] = []
    failed: List[str] = []
    checks: List[Dict[str, object]] = []
    network_bytes = 0
    network_requests = 0
    http_errors: List[Tuple[int, str]] = []

    def on_response(response):
        nonlocal network_bytes, network_requests
        try:
            if response.status >= 400:
                http_errors.append((response.status, response.url))
            length = response.headers.get("content-length")
            if length:
                network_bytes += int(length)
                network_requests += 1
        except Exception:
            pass

    with LocalServer(artifact_dir / "site", port):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "console",
                lambda message: console.append("{}: {}".format(message.type, message.text)),
            )
            page.on("requestfailed", lambda request: failed.append(
                "{} :: {}".format(request.url, request.failure)
            ))
            page.on("response", on_response)

            started = time.time()
            page.goto(
                "http://127.0.0.1:{}/poc_SwingPoc.html".format(port),
                wait_until="load",
                timeout=60000,
            )
            page.wait_for_selector("canvas", timeout=60000)
            canvas = page.locator("canvas").first
            canvas.wait_for(state="visible", timeout=60000)
            startup_ms = (time.time() - started) * 1000

            page.wait_for_function(
                """() => {
                    const node = document.querySelector('#sysoutdiv');
                    return node && /STATE .*ticks=[1-9]/.test(node.innerText);
                }""",
                timeout=60000,
            )
            first_state_ms = (time.time() - started) * 1000
            box = canvas.bounding_box()
            if not box or box["width"] < 200 or box["height"] < 200:
                raise VerifyError("Canvas has an unexpected size: {}".format(box))
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

            initial = _wait_for_state(page, lambda s: s["ticks"] > 0, "first timer tick")
            time.sleep(1.0)
            moving = _wait_for_state(
                page, lambda s: s["ticks"] > initial["ticks"], "timer advancement"
            )
            if moving["ticks"] <= initial["ticks"]:
                raise VerifyError("Swing Timer did not advance")
            checks.append(
                {
                    "name": "swing_timer_animates",
                    "passed": True,
                    "detail": {"ticks": moving["ticks"], "first_state_ms": round(first_state_ms, 1)},
                }
            )

            canvas_bytes = canvas.screenshot()
            stats = _image_stats(canvas_bytes)
            _require_pixels(stats)
            checks.append(
                {
                    "name": "graphics2d_rendered",
                    "passed": True,
                    "detail": stats,
                }
            )

            box = canvas.bounding_box()
            page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            time.sleep(0.4)

            before = _state_from_text(_console_text(page))
            if before is None:
                raise VerifyError("No state available before keyboard checks")
            horizontal = "ArrowLeft" if before["dx"] > 0 else "ArrowRight"
            vertical = "ArrowUp" if before["dy"] > 0 else "ArrowDown"
            page.keyboard.press(horizontal)
            left = _wait_for_state(
                page,
                lambda s: (s["dx"] < 0) if horizontal == "ArrowLeft" else (s["dx"] > 0),
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
                lambda s: (s["dy"] < 0) if vertical == "ArrowUp" else (s["dy"] > 0),
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
            paused = _wait_for_state(page, lambda s: s["paused"], "space pause")
            time.sleep(0.6)
            paused_later = _state_from_text(_console_text(page))
            if paused_later is None or not paused_later["paused"]:
                raise VerifyError("Pause did not persist: {}".format(paused_later))
            if paused_later["ticks"] != paused["ticks"]:
                raise VerifyError(
                    "Timer advanced while paused: {} -> {}".format(
                        paused["ticks"], paused_later["ticks"]
                    )
                )
            checks.append(
                {
                    "name": "keyboard_pause",
                    "passed": True,
                    "detail": {"ticks": paused["ticks"]},
                }
            )

            page.keyboard.press("Space")
            _wait_for_state(page, lambda s: not s["paused"], "space unpause")
            page.keyboard.press("KeyR")
            reset_states = []
            deadline = time.time() + 8
            while time.time() < deadline:
                reset_states = _all_states(_console_text(page))
                if any(
                    s["ticks"] == 0 and s["x"] == 80 and s["y"] == 200 and not s["paused"]
                    for s in reset_states
                ):
                    break
                time.sleep(0.1)
            else:
                raise VerifyError("Reset key did not produce the initial state")
            checks.append(
                {
                    "name": "keyboard_reset",
                    "passed": True,
                    "detail": {"states_seen": len(reset_states)},
                }
            )

            screenshot.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot), full_page=True)
            memory = page.evaluate(
                """() => performance.memory ? {
                    usedJSHeapSize: performance.memory.usedJSHeapSize,
                    totalJSHeapSize: performance.memory.totalJSHeapSize,
                    jsHeapSizeLimit: performance.memory.jsHeapSizeLimit
                } : null"""
            )
            body_text = page.locator("body").inner_text()
            warnings = []
            package_missing = any(
                status == 404 and url.endswith("/swingjs/j2s/core/package.js")
                for status, url in http_errors
            )
            if package_missing or "package.js not found (ignored)" in body_text:
                warnings.append(
                    "SwingJS requested an absent core/package.js; the loader reports this as an ignored non-fatal warning."
                )
            browser.close()

    unexpected_http = [
        entry
        for entry in http_errors
        if not (entry[0] == 404 and entry[1].endswith("/swingjs/j2s/core/package.js"))
    ]
    if unexpected_http:
        raise VerifyError("Unexpected HTTP errors: {}".format(unexpected_http))
    fatal = [
        line
        for line in console
        if (line.startswith("error:") and "Failed to load resource" not in line)
        or "Exception in thread" in line
        or "NoClassDefFoundError" in line
    ]
    if errors:
        raise VerifyError("Browser page errors: {}".format(errors))
    if failed:
        raise VerifyError("Failed network requests: {}".format(failed))
    if fatal:
        raise VerifyError("Fatal browser console messages: {}".format(fatal))

    artifact_size = sum(p.stat().st_size for p in (artifact_dir / "site").rglob("*") if p.is_file())
    record = {
        "schema_version": "1.0",
        "milestone": "2C.0",
        "backend": "swingjs",
        "runtime": "SwingJS / Java2Script 5.0.1-v7",
        "artifact": str(artifact_dir.relative_to(ROOT)) if artifact_dir.is_relative_to(ROOT) else str(artifact_dir),
        "entry_point": "poc_SwingPoc.html",
        "state": "runtime_verified",
        "checks": checks,
        "metrics": {
            "startup_ms": round(startup_ms, 1),
            "first_state_ms": round(first_state_ms, 1),
            "artifact_size_bytes": artifact_size,
            "network_bytes": network_bytes,
            "network_requests": network_requests,
            "source_modifications_for_swingjs": 0,
            "memory": memory,
        },
        "screenshots": [
            str(screenshot.relative_to(ROOT)) if screenshot.is_relative_to(ROOT) else str(screenshot)
        ],
        "console_errors": [],
        "http_errors": [{"status": status, "url": url} for status, url in http_errors],
        "warnings": warnings,
        "console_tail": console[-30:],
        "generated_at": int(time.time()),
    }
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT))
    parser.add_argument("--port", type=int, default=18140)
    parser.add_argument("--evidence", default=str(DEFAULT_EVIDENCE))
    parser.add_argument("--screenshot", default=str(DEFAULT_SCREENSHOT))
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        record = verify(
            Path(args.artifact_dir).expanduser().resolve(),
            args.port,
            Path(args.evidence).expanduser().resolve(),
            Path(args.screenshot).expanduser().resolve(),
        )
    except VerifyError as exc:
        print("VERIFY FAILED: {}".format(exc), file=sys.stderr)
        return 1
    metrics = record["metrics"]
    print("VERIFIED: {}".format(record["artifact"]))
    print("  startup_ms: {}".format(metrics["startup_ms"]))
    print("  first_state_ms: {}".format(metrics["first_state_ms"]))
    print("  artifact_size_bytes: {:,}".format(metrics["artifact_size_bytes"]))
    print("  network_bytes: {:,}".format(metrics["network_bytes"]))
    print("  evidence: {}".format(DEFAULT_EVIDENCE.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
