"""CheerpJ 5.0 Backend Adapter and Web Artifact Generator for Provikom Converter."""

from __future__ import annotations

import html
import json
import posixpath
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from provikom_converter.adapters.base import (
    BackendAdapter,
    BuildOptions,
    BuildResult,
    ConversionOptions,
    ConversionPlan,
    ConversionStep,
    MissingDependencyError,
    StagedDependency,
    UnsupportedRuntimeError,
)
from provikom_converter.analyzer.archive import ArchiveInventory
from provikom_converter.analyzer.bytecode import java_version_from_major
from provikom_converter.analyzer.compatibility import (
    BackendEvaluation,
    CompatibilityEvaluator,
    CompatibilityStatus,
)
from provikom_converter.analyzer.rules import AnalysisFeatures
from provikom_converter.artifacts.report import calculate_sha256
from provikom_converter.build_safety import (
    OWNERSHIP_MARKER_FILENAME,
    atomic_output_directory,
    refresh_ownership_marker,
    validate_output_directory,
)
from provikom_converter.lifecycle import built_artifact_lifecycle
from provikom_converter.version import __version__


MANIFEST_SCHEMA_VERSION = "1.1"
CHEERPJ_CDN_LOADER = "https://cjrtnc.leaningtech.com/5.0/loader.js"


def select_cheerpj_runtime(max_major: int) -> Tuple[int, str, bool]:
    """Select the CheerpJ 5.0 Java runtime for a class-file major version.

    Mapping:
      - Java 8 bytecode (major <= 52)  -> Java 8 runtime
      - Java 9-21 bytecode (53-65)     -> Java 21 LTS runtime
      - Java 22 bytecode (major 66)    -> Java 25 preview candidate (experimental)
      - Anything else                  -> UnsupportedRuntimeError
    """
    if max_major < 45:
        raise UnsupportedRuntimeError(
            f"Invalid or ancient bytecode major version {max_major}. "
            "The minimum supported version is 45 (Java 1.1)."
        )
    if max_major <= 52:
        return 8, "Java 8", False
    if max_major <= 65:
        return 21, "Java 21 (LTS)", False
    if max_major == 66:
        return 25, "Java 25 (Experimental Preview Candidate)", True

    ver_str = java_version_from_major(max_major)
    raise UnsupportedRuntimeError(
        f"Bytecode version {max_major} ({ver_str}) is not supported by CheerpJ 5.0. "
        "Supported targets are Java 8 (major <= 52), Java 9-21 (major 53-65), "
        "and Java 22 (major 66 via the Java 25 preview runtime)."
    )


def detect_entry_point(analysis_result: Any) -> Tuple[Optional[str], str, List[str]]:
    """Resolve the main class from the JAR manifest, falling back to bytecode scanning."""
    inventory: ArchiveInventory = analysis_result.inventory
    manifest = inventory.manifest
    if manifest and manifest.main_class:
        return manifest.main_class, "manifest", []

    candidates = sorted(
        {
            parsed.class_name.replace("/", ".")
            for parsed in analysis_result.parsed_classes
            if "main" in parsed.methods
        }
    )
    if len(candidates) == 1:
        return candidates[0], "bytecode_scan", candidates
    if len(candidates) > 1:
        return candidates[0], "bytecode_scan_ambiguous", candidates
    return None, "not_found", []


def _normalize_virtual_mount_root(value: str) -> str:
    root = value.strip() or "/app/"
    if not root.startswith("/"):
        root = "/" + root
    if not root.endswith("/"):
        root += "/"
    return root


def humanize_game_title(stem: str) -> str:
    title = re.sub(r"[_-]+", " ", stem)
    title = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", title)
    title = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", title)
    return title.title().strip()


def _normalize_dependency_path(entry: str) -> str:
    """Validate and normalize a manifest Class-Path entry into a relative path."""
    raw = entry.strip()
    if not raw:
        raise MissingDependencyError("Manifest Class-Path contains an empty entry.")
    if "://" in raw or raw.lower().startswith(("http:", "https:", "file:", "jar:")):
        raise MissingDependencyError(
            f"Manifest Class-Path entry '{entry}' is a remote/absolute URL. "
            "Stage the dependency locally next to the JAR instead."
        )

    normalized = raw.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized.startswith("/"):
        raise MissingDependencyError(
            f"Manifest Class-Path entry '{entry}' is an absolute path and cannot be staged safely."
        )

    normalized = posixpath.normpath(normalized)
    parts = [p for p in normalized.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        raise MissingDependencyError(
            f"Manifest Class-Path entry '{entry}' contains path traversal and was rejected."
        )
    return "/".join(parts)


def _dependency_candidates(source_dir: Path, dep_rel: str) -> List[Path]:
    dep_name = posixpath.basename(dep_rel)
    candidates = [
        source_dir / dep_rel,
        source_dir.parent / dep_rel,
        source_dir / dep_name,
        source_dir.parent / dep_name,
        source_dir / "lib" / dep_name,
        source_dir.parent / "lib" / dep_name,
        source_dir.parent / "games" / "lib" / dep_name,
    ]

    unique: List[Path] = []
    seen = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def _stage_jar_dependencies(
    inventory: ArchiveInventory,
    source_jar_path: Path,
    out_dir: Path,
    source_jar_dir: Optional[str],
    virtual_mount_root: str,
) -> Tuple[List[StagedDependency], List[Dict[str, Any]]]:
    staged: List[StagedDependency] = []
    records: List[Dict[str, Any]] = []

    class_path = inventory.manifest.class_path if inventory.manifest else []
    if not class_path:
        return staged, records

    source_dir = Path(source_jar_dir).resolve() if source_jar_dir else source_jar_path.parent
    out_root = out_dir.resolve()

    for entry in class_path:
        dep_rel = _normalize_dependency_path(entry)

        found_path: Optional[Path] = None
        checked: List[Path] = []
        for candidate in _dependency_candidates(source_dir, dep_rel):
            checked.append(candidate)
            if candidate.is_file():
                found_path = candidate.resolve()
                break

        if not found_path:
            checked_text = ", ".join(str(p) for p in checked)
            raise MissingDependencyError(
                f"Required manifest Class-Path dependency '{entry}' could not be found. "
                f"Looked in: {checked_text}"
            )

        dest_path = (out_root / dep_rel).resolve()
        if out_root != dest_path and out_root not in dest_path.parents:
            raise MissingDependencyError(
                f"Manifest Class-Path entry '{entry}' escapes the output directory and was rejected."
            )
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(found_path, dest_path)

        dep_bytes = found_path.read_bytes()
        virtual_path = virtual_mount_root + dep_rel
        staged.append(
            StagedDependency(
                source_path=str(found_path),
                relative_path=dep_rel,
                virtual_path=virtual_path,
                size_bytes=len(dep_bytes),
            )
        )
        records.append(
            {
                "relative_path": dep_rel,
                "virtual_path": virtual_path,
                "size_bytes": len(dep_bytes),
                "sha256": calculate_sha256(dep_bytes),
            }
        )

    return staged, records


def _serialize_compatibility(evaluation: Optional[BackendEvaluation]) -> Dict[str, Any]:
    if evaluation is None:
        return {
            "status": CompatibilityStatus.UNKNOWN.value,
            "summary": "No CheerpJ compatibility evaluation was available.",
        }
    return {
        "status": evaluation.status.value,
        "summary": evaluation.summary,
        "confidence_score": evaluation.confidence_score,
        "verified_capabilities": evaluation.verified_capabilities,
        "assumptions_and_risks": evaluation.assumptions_and_risks,
        "blockers": evaluation.blockers,
        "workarounds_needed": evaluation.workarounds_needed,
        "remediation_steps": evaluation.remediation_steps,
    }


def _collect_notes(
    *,
    is_experimental: bool,
    has_audio: bool,
    dependency_records: List[Dict[str, Any]],
    entry_source: str,
    entry_candidates: List[str],
    security_warnings: List[str],
    evaluation: Optional[BackendEvaluation],
) -> List[str]:
    notes: List[str] = []
    if is_experimental:
        notes.append(
            "Java 22 bytecode is executed on the Java 25 preview runtime. "
            "This path is experimental and may change with CheerpJ releases."
        )
    if has_audio:
        notes.append(
            "Audio requires a browser user gesture. Some javax.sound.sampled / Clip "
            "formats may be unsupported by the browser backend."
        )
    if dependency_records:
        paths = ", ".join(d["relative_path"] for d in dependency_records)
        notes.append(
            f"Manifest Class-Path dependencies are served from the web root and loaded via /app/: {paths}."
        )
    if entry_source == "bytecode_scan":
        notes.append("The Main-Class manifest attribute was missing; the entry point was inferred by scanning bytecode.")
    elif entry_source == "bytecode_scan_ambiguous":
        notes.append(
            "Multiple classes declare main(); the first candidate was selected: "
            + ", ".join(entry_candidates)
        )
    elif entry_source == "not_found":
        notes.append("No Main-Class was found in the manifest or bytecode. Launching may fail.")
    if evaluation is not None:
        notes.extend(evaluation.workarounds_needed)
        notes.extend(evaluation.assumptions_and_risks)
    for warning in security_warnings:
        notes.append(f"Archive security notice: {warning}")

    unique: List[str] = []
    seen = set()
    for note in notes:
        if note not in seen:
            seen.add(note)
            unique.append(note)
    return unique


def generate_player_html(
    game_title: str,
    game_jar_name: str,
    runtime_label: str,
    is_experimental: bool,
    has_audio: bool,
    notes: Optional[List[str]] = None,
    main_class: Optional[str] = None,
) -> str:
    badge_class = "badge-experimental" if is_experimental else "badge-lts"
    badge_text = f"Experimental: {runtime_label}" if is_experimental else runtime_label
    safe_title = html.escape(game_title)
    safe_jar = html.escape(game_jar_name)
    safe_badge = html.escape(badge_text)
    safe_main = html.escape(main_class) if main_class else "Auto-detected from manifest"

    notes_html = ""
    if notes:
        items = "".join(f"<li>{html.escape(note)}</li>" for note in notes)
        notes_html = f"""
              <div class="compat-notes">
                <h3>Compatibility notes</h3>
                <ul>{items}</ul>
              </div>"""

    start_description = (
        "Click to initialize the Java virtual machine and unlock audio."
        if has_audio
        else "Click to initialize the Java virtual machine."
    )

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="color-scheme" content="dark" />
    <title>{safe_title} — Provikom Web Player</title>
    <link rel="stylesheet" href="style.css" />
    <script src="{CHEERPJ_CDN_LOADER}"></script>
  </head>
  <body data-status="idle">
    <div id="player-app">
      <header class="player-header">
        <div class="header-left">
          <span class="brand-logo">Provikom</span>
          <h1 class="game-title">{safe_title}</h1>
          <span class="runtime-badge {badge_class}">{safe_badge}</span>
        </div>
        <div class="header-right">
          <button id="btn-fullscreen" class="btn-ctrl" type="button" title="Toggle Fullscreen">Fullscreen</button>
          <button id="btn-restart" class="btn-ctrl" type="button" title="Restart Game">Restart</button>
        </div>
      </header>

      <main class="player-main">
        <div id="canvas-container" class="canvas-container">
          <div id="cheerpj-display" class="cheerpj-display"></div>

          <div id="overlay-start" class="overlay-card overlay-start">
            <div class="overlay-content">
              <div class="game-icon">Game</div>
              <h2>Ready to Play {safe_title}</h2>
              <p class="overlay-desc">{start_description}</p>
              <dl class="game-meta">
                <div><dt>JAR</dt><dd>{safe_jar}</dd></div>
                <div><dt>Runtime</dt><dd>{html.escape(runtime_label)}</dd></div>
                <div><dt>Entry</dt><dd>{safe_main}</dd></div>
              </dl>
              <button id="btn-start" class="btn-action" type="button">Launch Game</button>{notes_html}
            </div>
          </div>

          <div id="overlay-loading" class="overlay-card overlay-loading hidden">
            <div class="overlay-content">
              <div class="spinner"></div>
              <h3 id="loading-heading">Initializing Runtime...</h3>
              <p id="loading-subtext" class="loading-subtext">Preparing the CheerpJ 5.0 WebAssembly container</p>
              <div class="progress-steps">
                <span id="step-env" class="step step-active">1. Runtime</span>
                <span id="step-deps" class="step">2. Dependencies</span>
                <span id="step-jar" class="step">3. Game Code</span>
                <span id="step-run" class="step">4. Launch</span>
              </div>
            </div>
          </div>

          <div id="overlay-error" class="overlay-card overlay-error hidden">
            <div class="overlay-content">
              <div class="error-icon">!</div>
              <h3 id="error-title">Startup Failed</h3>
              <p id="error-message" class="error-message"></p>
              <div class="error-actions">
                <button id="btn-retry" class="btn-action" type="button">Retry</button>
                <button id="btn-dismiss" class="btn-secondary" type="button">Dismiss</button>
                <button id="btn-copy-error" class="btn-secondary" type="button">Copy Details</button>
              </div>
              <pre id="error-details" class="error-details hidden"></pre>
            </div>
          </div>
        </div>
      </main>

      <footer class="player-footer">
        <div class="footer-info">
          <span>Target: <code>{safe_jar}</code></span>
          <span>Powered by <strong>Provikom Converter</strong> &amp; <strong>CheerpJ 5.0</strong></span>
        </div>
        <div class="footer-hints">
          <span class="hint-keyboard">Click inside the canvas to focus keyboard controls</span>
        </div>
      </footer>
    </div>

    <script src="app.js"></script>
  </body>
</html>
"""


def generate_player_css() -> str:
    return """/* Provikom Converter - Player Stylesheet */
:root {
  --bg-main: #0f1117;
  --bg-card: #1a1d27;
  --bg-header: #141721;
  --accent: #3b82f6;
  --accent-hover: #2563eb;
  --text-main: #f1f5f9;
  --text-muted: #94a3b8;
  --border: #2e3547;
  --success: #10b981;
  --warning: #f59e0b;
  --error: #ef4444;
}

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background-color: var(--bg-main);
  color: var(--text-main);
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

#player-app {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.player-header {
  min-height: 56px;
  background: var(--bg-header);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.5rem 1.25rem;
  flex-shrink: 0;
  flex-wrap: wrap;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.brand-logo {
  font-size: 0.85rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: linear-gradient(135deg, #60a5fa, #a855f7);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.game-title {
  font-size: 1.1rem;
  font-weight: 600;
}

.runtime-badge {
  font-size: 0.72rem;
  padding: 2px 8px;
  border-radius: 9999px;
  font-weight: 500;
}

.badge-lts {
  background: rgba(16, 185, 129, 0.15);
  color: #34d399;
  border: 1px solid rgba(16, 185, 129, 0.3);
}

.badge-experimental {
  background: rgba(245, 158, 11, 0.15);
  color: #fbbf24;
  border: 1px solid rgba(245, 158, 11, 0.3);
}

.header-right {
  display: flex;
  gap: 0.5rem;
}

.btn-ctrl {
  background: var(--bg-card);
  color: var(--text-main);
  border: 1px solid var(--border);
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 0.82rem;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-ctrl:hover {
  background: var(--border);
}

.player-main {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  overflow: hidden;
  background: radial-gradient(circle at center, #171b26 0%, #0d0f15 100%);
}

.canvas-container {
  position: relative;
  width: 100%;
  max-width: 960px;
  height: calc(100vh - 120px);
  max-height: 720px;
  background: #000;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.4);
  border: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
}

.cheerpj-display {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.cheerpj-display canvas {
  outline: none;
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.overlay-card {
  position: absolute;
  inset: 0;
  background: rgba(15, 17, 23, 0.94);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
  transition: opacity 0.2s ease;
  overflow-y: auto;
}

.overlay-content {
  text-align: center;
  max-width: 520px;
  padding: 2rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
}

.game-icon {
  font-size: 1.1rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--accent);
}

.overlay-desc {
  color: var(--text-muted);
  font-size: 0.92rem;
  line-height: 1.5;
}

.game-meta {
  width: 100%;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 0.5rem;
  font-size: 0.78rem;
}

.game-meta div {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.5rem;
}

.game-meta dt {
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-size: 0.66rem;
  margin-bottom: 0.2rem;
}

.game-meta dd {
  color: var(--text-main);
  word-break: break-word;
}

.compat-notes {
  width: 100%;
  text-align: left;
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.25);
  border-radius: 8px;
  padding: 0.75rem 1rem;
  font-size: 0.78rem;
  color: #fcd34d;
}

.compat-notes h3 {
  font-size: 0.8rem;
  margin-bottom: 0.4rem;
}

.compat-notes ul {
  margin-left: 1.1rem;
  display: grid;
  gap: 0.3rem;
}

.btn-action {
  background: var(--accent);
  color: #fff;
  border: none;
  padding: 10px 24px;
  border-radius: 8px;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 4px 6px -1px rgba(59, 130, 246, 0.4);
  transition: all 0.15s ease;
}

.btn-action:hover {
  background: var(--accent-hover);
  transform: translateY(-1px);
}

.btn-secondary {
  background: var(--bg-card);
  color: var(--text-main);
  border: 1px solid var(--border);
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 0.85rem;
  cursor: pointer;
}

.btn-secondary:hover {
  background: var(--border);
}

.spinner {
  width: 44px;
  height: 44px;
  border: 3px solid rgba(255, 255, 255, 0.1);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading-subtext {
  color: var(--text-muted);
  font-size: 0.88rem;
}

.progress-steps {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 0.5rem;
  margin-top: 0.75rem;
  font-size: 0.75rem;
}

.step {
  padding: 4px 8px;
  border-radius: 4px;
  background: var(--bg-card);
  color: var(--text-muted);
}

.step-active {
  background: var(--accent);
  color: #fff;
  font-weight: 600;
}

.step-done {
  background: rgba(16, 185, 129, 0.2);
  color: #34d399;
}

.error-icon {
  font-size: 1.6rem;
  font-weight: 700;
  color: var(--error);
}

.error-message {
  color: #fca5a5;
  font-size: 0.9rem;
}

.error-details {
  text-align: left;
  background: #050608;
  padding: 0.75rem;
  border-radius: 6px;
  border: 1px solid #3b1818;
  font-size: 0.75rem;
  color: #f87171;
  max-height: 220px;
  overflow-y: auto;
  width: 100%;
  white-space: pre-wrap;
}

.error-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 0.75rem;
}

.player-footer {
  min-height: 40px;
  background: var(--bg-header);
  border-top: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.5rem 1.25rem;
  font-size: 0.78rem;
  color: var(--text-muted);
  flex-shrink: 0;
  flex-wrap: wrap;
}

.player-footer code {
  color: #93c5fd;
}

.hint-keyboard {
  color: #cbd5e1;
}

.hidden {
  display: none !important;
}
"""


def generate_player_js(config: Dict[str, Any]) -> str:
    config_json = json.dumps(config, indent=2)
    template = """// Provikom Converter - CheerpJ 5.0 Runtime Controller
// Official APIs: cheerpjInit, cheerpjCreateDisplay, cheerpjRunJar, cheerpjRunMain

const CONFIG = __CONFIG_JSON__;

const FATAL_PATTERNS = [
  /ExceptionInInitializerError/,
  /NoClassDefFoundError/,
  /UnsatisfiedLinkError/,
  /No line matching interface/,
  /Exception in thread/,
  /Caused by:/
];

let initialized = false;
let starting = false;
let javaFailureReported = false;
let consoleBuffer = [];

function setStatus(status, detail) {
  document.body.dataset.status = status;
  if (detail) {
    document.body.dataset.statusDetail = detail;
  } else {
    delete document.body.dataset.statusDetail;
  }
}

function showOverlay(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove("hidden");
}

function hideOverlay(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add("hidden");
}

function updateLoadingStep(stepId, heading, subtext) {
  const steps = ["step-env", "step-deps", "step-jar", "step-run"];
  let passed = true;
  for (const step of steps) {
    const el = document.getElementById(step);
    if (!el) continue;
    if (step === stepId) {
      el.className = "step step-active";
      passed = false;
    } else if (passed) {
      el.className = "step step-done";
    } else {
      el.className = "step";
    }
  }
  if (heading) document.getElementById("loading-heading").textContent = heading;
  if (subtext) document.getElementById("loading-subtext").textContent = subtext;
}

function showError(title, message, details) {
  setStatus("error", title);
  hideOverlay("overlay-start");
  hideOverlay("overlay-loading");
  showOverlay("overlay-error");

  document.getElementById("error-title").textContent = title;
  document.getElementById("error-message").textContent = message;

  const detailsEl = document.getElementById("error-details");
  if (details) {
    detailsEl.textContent = details;
    detailsEl.classList.remove("hidden");
  } else {
    detailsEl.textContent = "";
    detailsEl.classList.add("hidden");
  }
  console.error("[Provikom Player Error]", title, message, details || "");
}

function reportJavaFailure() {
  if (javaFailureReported) return;
  javaFailureReported = true;

  const relevant = consoleBuffer.filter((line) =>
    FATAL_PATTERNS.some((pattern) => pattern.test(line))
  );
  const summary = relevant[0] || "The Java runtime reported an exception.";
  setStatus("error", "java-exception");
  showError(
    "Java Runtime Error Detected",
    "The Java process raised an exception. The game window may not appear or may not be playable.",
    (relevant.length ? relevant : consoleBuffer).join("\\n")
  );
  document.body.dataset.javaError = summary;
}

function installRuntimeDiagnostics() {
  const methods = ["log", "info", "warn", "error"];
  methods.forEach((method) => {
    const original = console[method];
    console[method] = (...args) => {
      const text = args.map((arg) => String(arg)).join(" ");
      if (text.startsWith("CheerpJ: Font remapping for")) return;
      consoleBuffer.push(text);
      if (consoleBuffer.length > 80) consoleBuffer.shift();
      if (FATAL_PATTERNS.some((pattern) => pattern.test(text))) {
        setTimeout(reportJavaFailure, 150);
      }
      original.apply(console, args);
    };
  });

  window.addEventListener("error", (event) => {
    showError("JavaScript Error", event.message || "Unexpected browser error", event.error ? String(event.error.stack || event.error) : null);
  });

  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason;
    showError("Unhandled Promise Rejection", String(reason && reason.message ? reason.message : reason), reason && reason.stack ? String(reason.stack) : null);
  });
}

async function assertFileAvailable(relativePath) {
  const url = new URL(relativePath, document.baseURI);
  const response = await fetch(url, { method: "HEAD", cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Required file not found (HTTP ${response.status}): ${url.pathname}`);
  }
}

function focusCanvas() {
  const display = document.getElementById("cheerpj-display");
  const canvas = display.querySelector("canvas");
  if (canvas) {
    canvas.tabIndex = 0;
    canvas.focus();
  }
}

async function launchGame() {
  if (starting) return;
  starting = true;

  hideOverlay("overlay-start");
  showOverlay("overlay-loading");
  setStatus("initializing");

  try {
    updateLoadingStep("step-env", "Initializing Java Runtime", `Configuring CheerpJ 5.0 (${CONFIG.runtimeLabel})...`);
    if (typeof cheerpjInit !== "function") {
      throw new Error("The CheerpJ loader script did not load. Check network access to the CheerpJ CDN.");
    }

    await cheerpjInit({ version: CONFIG.runtimeVersion, status: "none" });
    initialized = true;

    updateLoadingStep("step-deps", "Checking Dependencies", "Verifying files served from the /app/ mount...");
    await assertFileAvailable(CONFIG.gameJar);
    for (const dep of CONFIG.dependencies) {
      await assertFileAvailable(dep.relative_path);
    }

    updateLoadingStep("step-jar", "Mounting Game Archive", `Preparing ${CONFIG.gameJar}...`);
    const displayElement = document.getElementById("cheerpj-display");
    displayElement.replaceChildren();
    cheerpjCreateDisplay(-1, -1, displayElement);

    updateLoadingStep("step-run", "Starting Game", "Executing the Java entry point...");
    hideOverlay("overlay-loading");
    setStatus("running");
    setTimeout(focusCanvas, 250);

    let exitCode;
    if (CONFIG.mainClass) {
      exitCode = await cheerpjRunMain(CONFIG.mainClass, CONFIG.classPath.join(":"));
    } else {
      exitCode = await cheerpjRunJar(CONFIG.jarVirtualPath);
    }

    if (typeof exitCode === "number" && exitCode !== 0) {
      showError("Game Exited", `The Java process exited with code ${exitCode}.`, null);
    } else {
      setStatus("exited");
    }
  } catch (error) {
    showError("Launch Error", error && error.message ? error.message : String(error), error && error.stack ? String(error.stack) : null);
  } finally {
    starting = false;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  installRuntimeDiagnostics();
  setStatus("idle");

  document.getElementById("btn-start").addEventListener("click", launchGame);
  document.getElementById("btn-retry").addEventListener("click", () => window.location.reload());
  document.getElementById("btn-dismiss").addEventListener("click", () => {
    hideOverlay("overlay-error");
    setStatus(initialized ? "running" : "idle");
  });
  document.getElementById("btn-copy-error").addEventListener("click", () => {
    const text = document.getElementById("error-details").textContent;
    navigator.clipboard.writeText(text).then(
      () => alert("Error details copied to clipboard."),
      () => alert("Could not copy error details.")
    );
  });
  document.getElementById("btn-restart").addEventListener("click", () => window.location.reload());
  document.getElementById("btn-fullscreen").addEventListener("click", () => {
    const container = document.getElementById("canvas-container");
    if (!document.fullscreenElement) {
      container.requestFullscreen().catch((error) => console.warn("Fullscreen request denied:", error));
    } else {
      document.exitFullscreen();
    }
  });
});
"""
    return template.replace("__CONFIG_JSON__", config_json)


def _runtime_reason(max_major: int, runtime_version: int) -> str:
    java_label = java_version_from_major(max_major)
    if runtime_version == 8:
        return f"{java_label} bytecode (major {max_major}) mapped to the Java 8 runtime."
    if runtime_version == 21:
        return f"{java_label} bytecode (major {max_major}) mapped to the Java 21 LTS runtime."
    return (
        f"{java_label} bytecode (major {max_major}) mapped to the Java 25 preview runtime. "
        "This target is experimental."
    )


class CheerpJAdapter(BackendAdapter):
    """Adapter for Leaning Technologies CheerpJ JVM emulator."""

    @property
    def backend_id(self) -> str:
        return "cheerpj"

    @property
    def display_name(self) -> str:
        return "CheerpJ 5.0"

    @property
    def is_open_source(self) -> bool:
        return False

    @property
    def supports_bytecode_input(self) -> bool:
        return True

    @property
    def supports_source_input(self) -> bool:
        return False

    def evaluate_compatibility(
        self,
        inventory: ArchiveInventory,
        features: AnalysisFeatures,
        class_major_versions: List[int],
    ) -> BackendEvaluation:
        evaluator = CompatibilityEvaluator(inventory, features, class_major_versions)
        return evaluator.evaluate_cheerpj()

    def create_conversion_plan(
        self,
        inventory: ArchiveInventory,
        features: AnalysisFeatures,
        class_major_versions: List[int],
        options: ConversionOptions,
    ) -> ConversionPlan:
        eval_result = self.evaluate_compatibility(inventory, features, class_major_versions)
        is_feasible = eval_result.status in (
            CompatibilityStatus.SUPPORTED,
            CompatibilityStatus.SUPPORTED_WITH_WORKAROUNDS,
        )

        steps: List[ConversionStep] = []
        if is_feasible:
            steps.append(
                ConversionStep(
                    name="Stage Archive",
                    description="Copy the main JAR into the public web artifact directory.",
                    automated=True,
                )
            )

            if inventory.manifest and inventory.manifest.class_path:
                steps.append(
                    ConversionStep(
                        name="Resolve Class-Path Dependencies",
                        description=f"Stage external dependencies: {inventory.manifest.class_path}",
                        automated=True,
                    )
                )

            steps.append(
                ConversionStep(
                    name="Generate HTML Launcher",
                    description="Generate a responsive HTML5 web shell with the CheerpJ 5.0 loader.",
                    automated=True,
                )
            )
            steps.append(
                ConversionStep(
                    name="Synthesize Runtime Controller",
                    description="Generate app.js with cheerpjInit, cheerpjCreateDisplay, and /app/ execution.",
                    automated=True,
                )
            )

        return ConversionPlan(
            backend_id=self.backend_id,
            is_feasible=is_feasible,
            summary=eval_result.summary,
            steps=steps,
            required_tools=["cheerpj-loader"],
            estimated_difficulty="trivial" if eval_result.status == CompatibilityStatus.SUPPORTED else "low",
        )

    def generate_artifact(
        self,
        analysis_result: Any,
        options: BuildOptions,
    ) -> BuildResult:
        """Produce a complete, self-contained CheerpJ 5.0 static web artifact."""
        source_jar_path = Path(analysis_result.target_path).resolve()
        raw_output_dir = Path(options.output_directory).expanduser()

        # Validate the raw caller path before any resolve() call. Resolving here
        # first would follow a symlinked output directory and hide it from the
        # symlink rejection in build_safety.
        _validated_source, final_output_dir = validate_output_directory(
            source_jar_path, raw_output_dir
        )

        with atomic_output_directory(
            source_jar_path=source_jar_path,
            output_directory=raw_output_dir,
            force_overwrite=options.force_overwrite,
        ) as build_dir:
            return self._generate_artifact_into(
                analysis_result=analysis_result,
                options=options,
                out_dir=build_dir,
                final_output_dir=final_output_dir,
            )

    def _generate_artifact_into(
        self,
        analysis_result: Any,
        options: BuildOptions,
        out_dir: Path,
        final_output_dir: Path,
    ) -> BuildResult:
        inventory: ArchiveInventory = analysis_result.inventory
        majors = [pc.major_version for pc in analysis_result.parsed_classes]
        max_major = max(majors) if majors else 52

        runtime_version, runtime_label, is_experimental = select_cheerpj_runtime(max_major)
        virtual_mount_root = _normalize_virtual_mount_root(options.virtual_mount_root)

        source_jar_path = Path(analysis_result.target_path).resolve()
        dest_jar_path = out_dir / source_jar_path.name
        shutil.copy2(source_jar_path, dest_jar_path)

        staged_deps, dependency_records = _stage_jar_dependencies(
            inventory=inventory,
            source_jar_path=source_jar_path,
            out_dir=out_dir,
            source_jar_dir=options.source_jar_dir,
            virtual_mount_root=virtual_mount_root,
        )

        main_class, entry_source, entry_candidates = detect_entry_point(analysis_result)
        main_jar_virtual_path = virtual_mount_root + source_jar_path.name
        class_path = [main_jar_virtual_path] + [dep.virtual_path for dep in staged_deps]

        game_title = options.game_title or humanize_game_title(source_jar_path.stem)
        has_audio = bool(analysis_result.features.audio_apis)
        evaluation = None
        try:
            evaluation = analysis_result.evaluations.get("cheerpj")
        except Exception:
            evaluation = None

        notes = _collect_notes(
            is_experimental=is_experimental,
            has_audio=has_audio,
            dependency_records=dependency_records,
            entry_source=entry_source,
            entry_candidates=entry_candidates,
            security_warnings=inventory.security_warnings,
            evaluation=evaluation,
        )

        html_content = generate_player_html(
            game_title=game_title,
            game_jar_name=source_jar_path.name,
            runtime_label=runtime_label,
            is_experimental=is_experimental,
            has_audio=has_audio,
            notes=notes,
            main_class=main_class,
        )
        (out_dir / "index.html").write_text(html_content, encoding="utf-8")
        (out_dir / "style.css").write_text(generate_player_css(), encoding="utf-8")

        js_config = {
            "gameJar": source_jar_path.name,
            "runtimeVersion": runtime_version,
            "runtimeLabel": runtime_label,
            "isExperimental": is_experimental,
            "mainClass": main_class,
            "classPath": class_path,
            "virtualMountRoot": virtual_mount_root,
            "jarVirtualPath": main_jar_virtual_path,
            "dependencies": dependency_records,
        }
        (out_dir / "app.js").write_text(generate_player_js(js_config), encoding="utf-8")

        generated_files = [
            "index.html",
            "style.css",
            "app.js",
            "manifest.json",
            OWNERSHIP_MARKER_FILENAME,
            source_jar_path.name,
        ] + [dep.relative_path for dep in staged_deps]

        generated_at = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

        manifest_data: Dict[str, Any] = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "generated_at": generated_at,
            "provikom_converter_version": __version__,
            "backend": self.backend_id,
            "backend_display_name": self.display_name,
            "runtime_version": runtime_version,
            "is_experimental": is_experimental,
            "runtime": {
                "version": runtime_version,
                "label": runtime_label,
                "experimental": is_experimental,
                "selection_reason": _runtime_reason(max_major, runtime_version),
            },
            "entry_point": "index.html",
            "jar_file": source_jar_path.name,
            "java_major_version": max_major,
            "lifecycle": built_artifact_lifecycle(),
            "game": {
                "title": game_title,
                "jar_file": source_jar_path.name,
                "sha256": calculate_sha256(source_jar_path.read_bytes()),
                "size_bytes": source_jar_path.stat().st_size,
                "main_class": main_class,
                "entry_point_source": entry_source,
                "entry_point_candidates": entry_candidates,
                "java_major_version": max_major,
                "java_version": java_version_from_major(max_major),
                "has_audio": has_audio,
                "gui_apis": sorted({f.name for f in analysis_result.features.gui_frameworks}),
                "audio_apis": sorted({f.name for f in analysis_result.features.audio_apis}),
            },
            "compatibility": _serialize_compatibility(evaluation),
            "paths": {
                "web_root": "/",
                "virtual_mount_root": virtual_mount_root,
                "main_jar": source_jar_path.name,
                "main_jar_virtual_path": main_jar_virtual_path,
                "class_path": class_path,
            },
            "dependencies": dependency_records,
            "notes": notes,
            "generated_files": generated_files,
            "ownership": {
                "owner": "provikom-converter",
                "artifact_id": uuid.uuid4().hex,
                "marker": OWNERSHIP_MARKER_FILENAME,
            },
        }

        manifest_file = out_dir / "manifest.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
        if not refresh_ownership_marker(out_dir):
            raise RuntimeError("Failed to write artifact ownership marker")

        return BuildResult(
            backend_id=self.backend_id,
            output_directory=str(final_output_dir),
            entry_html=str(final_output_dir / "index.html"),
            game_jar_name=source_jar_path.name,
            game_title=game_title,
            runtime_version=runtime_version,
            runtime_label=runtime_label,
            is_experimental=is_experimental,
            staged_dependencies=staged_deps,
            generated_files=generated_files,
            manifest_path=str(final_output_dir / "manifest.json"),
            metadata=manifest_data,
        )

    def get_runtime_dependencies(self) -> List[str]:
        return [CHEERPJ_CDN_LOADER]
