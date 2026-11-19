#!/usr/bin/env python3
"""Benchmark the same SwingPoc under SwingJS and CheerpJ in Chromium.

SwingJS is served from the generated build artifact. CheerpJ is served from a
minimal wrapper that loads the CheerpJ runtime from the official CDN. Both
measurements use a fresh browser context and Network.loadingFinished bytes.
"""

from __future__ import annotations

import argparse
import functools
import io
import json
import re
import shutil
import socketserver
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_ARTIFACT = ROOT / "build" / "swingjs-poc"
DEFAULT_HARNESS = ROOT / "tools" / "swingjs" / "cheerpj-harness"
DEFAULT_EVIDENCE = ROOT / "docs" / "verification" / "swingjs-benchmark.json"
STATE_RE = re.compile(
    r"STATE x=(-?\d+) y=(-?\d+) dx=(-?\d+) dy=(-?\d+) paused=(true|false) ticks=(\d+)"
)


class BenchmarkError(RuntimeError):
    pass


class LocalServer:
    def __init__(self, directory: Path, port: int = 0):
        from provikom_converter.server import RangeRequestHandler

        class Handler(RangeRequestHandler):
            def log_message(self, fmt, *args):
                pass

        socketserver.ThreadingTCPServer.allow_reuse_address = True
        self.server = socketserver.ThreadingTCPServer(
            ("127.0.0.1", port),
            functools.partial(Handler, directory=str(directory)),
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


def _wait_for_state(
    state_source,
    predicate,
    label: str,
    timeout: float = 60.0,
    interval: float = 0.1,
    pump=None,
) -> Dict[str, object]:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        if pump is not None:
            pump()
        else:
            time.sleep(interval)
        last = _state_from_text(state_source())
        if last is not None and predicate(last):
            return last
    raise BenchmarkError("Timed out waiting for {} (last: {})".format(label, last))


def _image_stats(data: bytes) -> Dict[str, float]:
    from PIL import Image

    image = Image.open(io.BytesIO(data)).convert("RGB")
    sample = image.resize((120, 90))
    raw = sample.tobytes()
    pixels = list(zip(raw[0::3], raw[1::3], raw[2::3]))
    luminances = [0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b in pixels]
    mean = sum(luminances) / len(luminances)
    variance = sum((value - mean) ** 2 for value in luminances) / len(luminances)
    return {
        "unique_colors": float(len(set(pixels))),
        "luminance_stddev": round(variance ** 0.5, 3),
        "non_dark_ratio": round(sum(1 for p in pixels if max(p) > 24) / len(pixels), 4),
    }


def _dir_size(directory: Path) -> Tuple[int, int]:
    files = [p for p in directory.rglob("*") if p.is_file()]
    return sum(p.stat().st_size for p in files), len(files)


def _measure(
    playwright,
    name: str,
    url: str,
    state_source_factory,
    screenshot: Path,
    expected_canvas: Tuple[int, int],
) -> Dict[str, object]:
    browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    cdp = context.new_cdp_session(page)
    network_bytes = 0
    network_requests = 0
    http_errors: List[Tuple[int, str]] = []
    logs: List[str] = []
    page_errors: List[str] = []
    failed_requests: List[str] = []

    def on_loading_finished(params):
        nonlocal network_bytes
        network_bytes += int(params.get("encodedDataLength") or 0)

    def on_request(params):
        nonlocal network_requests
        network_requests += 1

    cdp.on("Network.loadingFinished", on_loading_finished)
    cdp.on("Network.requestWillBeSent", on_request)
    cdp.send("Network.enable")
    page.on("console", lambda message: logs.append("{}: {}".format(message.type, message.text)))
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on("requestfailed", lambda request: failed_requests.append(
        "{} :: {}".format(request.url, request.failure)
    ))
    page.on("response", lambda response: http_errors.append((response.status, response.url))
            if response.status >= 400 else None)

    started = time.time()
    page.goto(url, wait_until="load", timeout=60000)
    page.wait_for_selector("canvas", timeout=60000)
    canvas = page.locator("canvas").first
    canvas.wait_for(state="visible", timeout=60000)
    canvas_ms = (time.time() - started) * 1000
    box = canvas.bounding_box()
    if not box:
        raise BenchmarkError("Canvas has no bounding box")
    width, height = int(box["width"]), int(box["height"])
    if abs(width - expected_canvas[0]) > 2 or abs(height - expected_canvas[1]) > 2:
        raise BenchmarkError(
            "Unexpected canvas size {}x{}, expected {}x{}".format(
                width, height, expected_canvas[0], expected_canvas[1]
            )
        )

    state_source = state_source_factory(page, logs)
    pump = lambda: page.wait_for_timeout(100)
    first = _wait_for_state(
        state_source,
        lambda s: s["ticks"] > 0,
        "{} first timer tick".format(name),
        timeout=120.0,
        pump=pump,
    )
    first_state_ms = (time.time() - started) * 1000
    page.wait_for_timeout(1000)
    later = _wait_for_state(
        state_source,
        lambda s: s["ticks"] > first["ticks"],
        "timer advancement",
        pump=pump,
    )
    stats = _image_stats(canvas.screenshot())
    if stats["unique_colors"] < 20 or stats["luminance_stddev"] < 5:
        raise BenchmarkError("Canvas appears blank: {}".format(stats))

    heap = page.evaluate(
        """() => performance.memory ? {
            usedJSHeapSize: performance.memory.usedJSHeapSize,
            totalJSHeapSize: performance.memory.totalJSHeapSize,
            jsHeapSizeLimit: performance.memory.jsHeapSizeLimit
        } : null"""
    )
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(screenshot), full_page=True)
    time.sleep(0.3)
    unexpected = [
        entry
        for entry in http_errors
        if not (entry[0] == 404 and entry[1].endswith("/swingjs/j2s/core/package.js"))
    ]
    fatal = [
        line
        for line in logs
        if (line.startswith("error:") and "Failed to load resource" not in line)
        or "Exception in thread" in line
        or "NoClassDefFoundError" in line
    ]
    context.close()
    browser.close()
    if page_errors:
        raise BenchmarkError("Page errors: {}".format(page_errors))
    if failed_requests:
        raise BenchmarkError("Failed requests: {}".format(failed_requests))
    if unexpected:
        raise BenchmarkError("HTTP errors: {}".format(unexpected))
    if fatal:
        raise BenchmarkError("Fatal console messages: {}".format(fatal))
    return {
        "startup_ms": round(canvas_ms, 1),
        "first_state_ms": round(first_state_ms, 1),
        "network_bytes": network_bytes,
        "network_requests": network_requests,
        "memory": heap,
        "visual": stats,
        "canvas": {"width": width, "height": height},
        "ticks": later["ticks"],
        "http_errors": [{"status": s, "url": u} for s, u in http_errors],
        "console_errors": fatal,
        "screenshot": str(screenshot.relative_to(ROOT)) if screenshot.is_relative_to(ROOT) else str(screenshot),
    }


def _median(values: List[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _summarize(runs: List[Dict[str, object]]) -> Dict[str, object]:
    result = dict(runs[-1])
    for key in ("startup_ms", "first_state_ms", "network_bytes", "network_requests"):
        values = [float(run[key]) for run in runs]
        value = _median(values)
        result[key] = int(value) if key in ("network_bytes", "network_requests") else round(value, 1)
        result[key + "_min"] = min(values)
        result[key + "_max"] = max(values)
    memory_runs = [run["memory"] for run in runs if run.get("memory")]
    if memory_runs:
        result["memory"] = {
            key: int(_median([float(mem[key]) for mem in memory_runs]))
            for key in ("usedJSHeapSize", "totalJSHeapSize", "jsHeapSizeLimit")
        }
    result["runs"] = runs
    return result


def benchmark(
    swingjs_artifact: Path,
    harness: Path,
    evidence: Path,
    runs: int = 3,
) -> Dict[str, object]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BenchmarkError("Playwright is required (pip install -e '.[browser]')") from exc
    try:
        import PIL  # noqa: F401
    except ImportError as exc:
        raise BenchmarkError("Pillow is required (pip install -e '.[browser]')") from exc

    swingjs_site = swingjs_artifact / "site"
    poc_jar = swingjs_artifact / "SwingPoc.jar"
    if not (swingjs_site / "poc_SwingPoc.html").is_file() or not poc_jar.is_file():
        raise BenchmarkError("Run build_swingjs_poc.py first; missing artifact in {}".format(swingjs_artifact))

    shots = ROOT / "docs" / "screenshots"
    with tempfile.TemporaryDirectory(prefix="cheerpj-bench-") as temp:
        cheerpj_dir = Path(temp) / "site"
        shutil.copytree(str(harness), str(cheerpj_dir))
        shutil.copy2(str(poc_jar), str(cheerpj_dir / "SwingPoc.jar"))

        swingjs_size, swingjs_files = _dir_size(swingjs_site)
        cheerpj_size, cheerpj_files = _dir_size(cheerpj_dir)
        swingjs_runs: List[Dict[str, object]] = []
        cheerpj_runs: List[Dict[str, object]] = []
        with sync_playwright() as playwright:
            with LocalServer(swingjs_site) as swingjs_server, \
                    LocalServer(cheerpj_dir) as cheerpj_server:
                for iteration in range(runs):
                    order = ("swingjs", "cheerpj") if iteration % 2 == 0 else ("cheerpj", "swingjs")
                    for backend in order:
                        if backend == "swingjs":
                            swingjs_runs.append(_measure(
                                playwright,
                                "swingjs",
                                "http://127.0.0.1:{}/poc_SwingPoc.html".format(swingjs_server.port),
                                lambda page, logs: lambda: page.locator("#sysoutdiv").inner_text(),
                                shots / "swingjs-benchmark.png",
                                (720, 540),
                            ))
                        else:
                            cheerpj_runs.append(_measure(
                                playwright,
                                "cheerpj",
                                "http://127.0.0.1:{}/index.html".format(cheerpj_server.port),
                                lambda page, logs: lambda: "\n".join(logs),
                                shots / "cheerpj-benchmark.png",
                                (720, 540),
                            ))
        swingjs = _summarize(swingjs_runs)
        cheerpj = _summarize(cheerpj_runs)
        swingjs["artifact_size_bytes"] = swingjs_size
        swingjs["artifact_file_count"] = swingjs_files
        cheerpj["artifact_size_bytes"] = cheerpj_size
        cheerpj["artifact_file_count"] = cheerpj_files

    record = {
        "schema_version": "1.0",
        "milestone": "2C.0",
        "application": "SwingPoc (JFrame, JPanel, Graphics2D, Swing Timer, keyboard)",
        "source": "examples/swing-poc",
        "source_modifications": 0,
        "browser": "Chromium (Playwright headless)",
        "notes": [
            "Both runs auto-start the application; the production CheerpJ adapter normally waits for a user click.",
            "network_bytes is the Chromium CDP Network.loadingFinished payload for a fresh context; it includes the CheerpJ CDN runtime.",
            "artifact_size_bytes is the locally deployed artifact and excludes the CheerpJ runtime fetched from the CDN.",
            "SwingJS 404 for swingjs/j2s/core/package.js is a known non-fatal loader warning.",
            "Each backend was measured {} times in alternating order; reported timings/bytes are medians.".format(runs),
        ],
        "results": {
            "swingjs": swingjs,
            "cheerpj": cheerpj,
        },
        "comparison": {
            "startup_ratio_cheerpj_over_swingjs": round(
                cheerpj["startup_ms"] / swingjs["startup_ms"], 2
            ),
            "first_state_ratio_cheerpj_over_swingjs": round(
                cheerpj["first_state_ms"] / swingjs["first_state_ms"], 2
            ),
            "network_ratio_cheerpj_over_swingjs": round(
                cheerpj["network_bytes"] / max(1, swingjs["network_bytes"]), 2
            ),
        },
        "generated_at": int(time.time()),
    }
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--swingjs-artifact-dir", default=str(DEFAULT_ARTIFACT))
    parser.add_argument("--cheerpj-harness", default=str(DEFAULT_HARNESS))
    parser.add_argument("--evidence", default=str(DEFAULT_EVIDENCE))
    parser.add_argument("--runs", type=int, default=3)
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        record = benchmark(
            Path(args.swingjs_artifact_dir).expanduser().resolve(),
            Path(args.cheerpj_harness).expanduser().resolve(),
            Path(args.evidence).expanduser().resolve(),
            runs=max(1, args.runs),
        )
    except BenchmarkError as exc:
        print("BENCHMARK FAILED: {}".format(exc), file=sys.stderr)
        return 1
    print("{:<10} {:>12} {:>15} {:>15} {:>15}".format(
        "backend", "startup_ms", "first_state_ms", "network_MB", "artifact_MB"))
    for name in ("swingjs", "cheerpj"):
        result = record["results"][name]
        print("{:<10} {:>12.1f} {:>15.1f} {:>15.2f} {:>15.2f}".format(
            name,
            result["startup_ms"],
            result["first_state_ms"],
            result["network_bytes"] / 1_000_000,
            result["artifact_size_bytes"] / 1_000_000,
        ))
    print("evidence: {}".format(Path(args.evidence)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
