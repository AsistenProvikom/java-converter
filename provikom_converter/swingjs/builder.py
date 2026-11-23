"""Build a source-backed SwingJS artifact using the pinned Java2Script toolchain."""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import tempfile
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from provikom_converter.adapters.base import BuildResult
from provikom_converter.build_safety import (
    OWNERSHIP_MARKER_FILENAME,
    OWNERSHIP_OWNER,
    atomic_source_output_directory,
    refresh_ownership_marker,
)
from provikom_converter.lifecycle import built_artifact_lifecycle
from provikom_converter.swingjs import pins
from provikom_converter.swingjs.source import (
    SourceProject,
    SourceProjectError,
    inspect_source_project,
)
from provikom_converter.swingjs.toolchain import (
    SwingJSToolchain,
    SwingJSToolchainError,
    resolve_toolchain,
)
from provikom_converter.version import __version__

PLUGIN_ID = "provikom.j2s.builder"
PLUGIN_JAR = PLUGIN_ID + ".jar"
PACKAGE_ROOT = Path(__file__).resolve().parent
PLUGIN_SOURCE = PACKAGE_ROOT / "headless_builder"
J2S_TIMESTAMP_RE = re.compile(
    r"(//Created )\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}( Java2ScriptVisitor)"
)


class SwingJSBuildError(RuntimeError):
    """Raised when source transpilation or artifact packaging fails."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _run(
    command: List[str],
    *,
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: int = 300,
    log_path: Optional[Path] = None,
) -> subprocess.CompletedProcess:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            env=merged,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SwingJSBuildError(
            "Command failed to start or timed out: {}\n{}".format(" ".join(command), exc)
        ) from exc
    output = (result.stdout or "") + (result.stderr or "")
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(output, encoding="utf-8")
    if result.returncode != 0:
        raise SwingJSBuildError(
            "Command failed ({}): {}\n{}".format(
                result.returncode, " ".join(command), output[-6000:]
            )
        )
    return result


def _safe_name(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._")
    return value or "SwingProject"


def _copy_project(project: SourceProject, destination: Path) -> None:
    """Stage only inspected Java sources, not unrelated project files.

    This source-backed Java 8 subset expects src/**/*.java only. Copying an
    entire project would follow otherwise-unchecked non-Java symlinks.
    """
    destination.mkdir(parents=True, exist_ok=False)
    for source in project.java_files:
        relative = source.relative_to(project.root)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _write_eclipse_metadata(project: SourceProject, directory: Path) -> None:
    name = _safe_name(project.root.name)
    (directory / ".project").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<projectDescription>
  <name>{name}</name>
  <comment>Provikom SwingJS source build</comment>
  <projects></projects>
  <buildSpec>
    <buildCommand>
      <name>org.eclipse.jdt.core.javabuilder</name>
      <arguments></arguments>
    </buildCommand>
  </buildSpec>
  <natures>
    <nature>org.eclipse.jdt.core.javanature</nature>
  </natures>
</projectDescription>
""".format(name=name),
        encoding="utf-8",
    )
    (directory / ".classpath").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<classpath>
  <classpathentry kind="src" path="src"/>
  <classpathentry kind="con" path="org.eclipse.jdt.launching.JRE_CONTAINER"/>
  <classpathentry kind="output" path="bin"/>
</classpath>
""",
        encoding="utf-8",
    )
    settings = directory / ".settings"
    settings.mkdir(exist_ok=True)
    (directory / ".j2s").write_text(
        "j2s.compiler.status=enable\n", encoding="utf-8"
    )
    (settings / "org.eclipse.jdt.core.prefs").write_text(
        """eclipse.preferences.version=1
org.eclipse.jdt.core.compiler.codegen.targetPlatform=1.8
org.eclipse.jdt.core.compiler.compliance=1.8
org.eclipse.jdt.core.compiler.release=disabled
org.eclipse.jdt.core.compiler.source=1.8
""",
        encoding="utf-8",
    )


def _build_plugin(toolchain: SwingJSToolchain, work: Path) -> Path:
    classes = work / "plugin-classes"
    if classes.exists():
        shutil.rmtree(classes)
    classes.mkdir(parents=True)
    source = PLUGIN_SOURCE / "provikom" / "j2s" / "builder" / "ImportAndBuildApplication.java"
    if not source.is_file():
        raise SwingJSBuildError("Packaged headless builder source is missing: {}".format(source))
    classpath = os.pathsep.join(
        str(path) for path in sorted((toolchain.eclipse_home / "plugins").glob("*.jar"))
    )
    _run(
        [
            str(toolchain.javac),
            "-source",
            "17",
            "-target",
            "17",
            "-cp",
            classpath,
            "-d",
            str(classes),
            str(source),
        ],
        log_path=work / "javac-plugin.log",
    )
    shutil.copy2(PLUGIN_SOURCE / "plugin.xml", classes / "plugin.xml")
    manifest_dir = classes / "META-INF"
    manifest_dir.mkdir(exist_ok=True)
    shutil.copy2(PLUGIN_SOURCE / "META-INF" / "MANIFEST.MF", manifest_dir / "MANIFEST.MF")
    plugin_jar = work / PLUGIN_JAR
    _run(
        [
            str(toolchain.java_home / "bin" / "jar"),
            "cfm",
            str(plugin_jar),
            str(manifest_dir / "MANIFEST.MF"),
            "-C",
            str(classes),
            ".",
        ],
        log_path=work / "jar-plugin.log",
    )
    dropins = toolchain.eclipse_home / "dropins"
    dropins.mkdir(parents=True, exist_ok=True)
    shutil.copy2(plugin_jar, dropins / PLUGIN_JAR)
    return plugin_jar


def _compile_sources(project: SourceProject, toolchain: SwingJSToolchain, work: Path) -> Path:
    classes = work / "classes"
    classes.mkdir(parents=True, exist_ok=True)
    source_files = [str(path) for path in project.java_files]
    _run(
        [str(toolchain.javac), "--release", "8", "-proc:none", "-d", str(classes)] + source_files,
        log_path=work / "javac-sources.log",
    )
    return classes


def _extract_runtime(toolchain: SwingJSToolchain, site_dir: Path, log_path: Path) -> None:
    site_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(toolchain.site_zip) as archive:
            for member in archive.infolist():
                name = member.filename.replace("\\", "/")
                normalized = posixpath.normpath(name)
                if normalized.startswith("../") or normalized.startswith("/") or ".." in normalized.split("/"):
                    raise SwingJSBuildError(
                        "Pinned runtime archive contains an unsafe path: {}".format(name)
                    )
                archive.extract(member, site_dir)
    except (OSError, zipfile.BadZipFile) as exc:
        raise SwingJSBuildError(
            "Could not extract pinned SwingJS runtime {}: {}".format(toolchain.site_zip, exc)
        ) from exc
    (log_path).write_text(
        "Extracted pinned runtime {}\nSHA-256: {}\n".format(
            toolchain.site_zip.name, pins.SWINGJS_RUNTIME_SHA256
        ),
        encoding="utf-8",
    )


def _run_eclipse_build(
    toolchain: SwingJSToolchain,
    work: Path,
    workspace: Path,
    work_project: Path,
) -> Path:
    log_path = work / "eclipse.log"
    _run(
        [
            str(toolchain.eclipse_launcher),
            "-nosplash",
            "-clean",
            "-consoleLog",
            "-data",
            str(workspace),
            "-application",
            "{}.application".format(PLUGIN_ID),
            "-vm",
            str(toolchain.java),
            "-vmargs",
            "-Dprovikom.project={}".format(work_project),
        ],
        timeout=300,
        log_path=log_path,
    )
    output = log_path.read_text(encoding="utf-8", errors="replace")
    if "PROVIKOM_BUILD_OK" not in output:
        raise SwingJSBuildError(
            "Headless Eclipse Java2Script build did not report success.\n{}".format(
                output[-8000:]
            )
        )
    if "J2S SwingJS plugin processed" not in output:
        raise SwingJSBuildError(
            "Eclipse log does not show a Java2Script transpile result.\n{}".format(
                output[-8000:]
            )
        )
    return log_path


def _normalize_generated_output(site: Path) -> None:
    """Remove Java2Script's wall-clock comment so source builds are reproducible."""
    j2s = site / "swingjs" / "j2s"
    if not j2s.is_dir():
        return
    for path in sorted(j2s.rglob("*.js")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        updated = J2S_TIMESTAMP_RE.sub(r"\1reproducible\2", text)
        if updated != text:
            path.write_text(updated, encoding="utf-8")


def _find_generated_entry(site: Path, main_class: str) -> Tuple[Path, Path]:
    html_candidates: List[Path] = []
    main_pattern = re.compile(r"main\s*:\s*[\"']" + re.escape(main_class) + r"[\"']")
    for path in sorted(site.glob("*.html")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if main_pattern.search(text):
            html_candidates.append(path)
    if not html_candidates:
        raise SwingJSBuildError(
            "No generated HTML entry references main class {}. Generated files: {}".format(
                main_class, ", ".join(path.name for path in sorted(site.glob("*.html")))
            )
        )
    if len(html_candidates) > 1:
        raise SwingJSBuildError(
            "Multiple generated HTML entries reference {}: {}. Select a unique entry point.".format(
                main_class, ", ".join(path.name for path in html_candidates)
            )
        )
    entry = html_candidates[0]

    package_path = main_class.replace(".", "/")
    js_candidates = [
        site / "swingjs" / "j2s" / (package_path + ".js"),
        site / "swingjs" / "j2s" / package_path / (main_class.rsplit(".", 1)[-1] + ".js"),
    ]
    js_path = next((path for path in js_candidates if path.is_file()), None)
    if js_path is None:
        matches = sorted((site / "swingjs" / "j2s").rglob(main_class.rsplit(".", 1)[-1] + ".js"))
        js_path = matches[0] if len(matches) == 1 else None
    if js_path is None or not js_path.is_file():
        raise SwingJSBuildError(
            "Generated JavaScript for {} was not found under site/swingjs/j2s/.".format(main_class)
        )
    js_bytes = js_path.read_bytes()
    simple = main_class.rsplit(".", 1)[-1].encode("utf-8")
    if len(js_bytes) < 1000 or b"Clazz.newClass" not in js_bytes or simple not in js_bytes:
        raise SwingJSBuildError(
            "Generated JavaScript does not contain the transpiled {} class: {}".format(
                main_class, js_path
            )
        )
    return entry, js_path


def _prepare_index(template: str, title: str) -> str:
    safe_title = re.sub(r"<[^>]*>", "", title)
    updated = re.sub(
        r"<title>.*?</title>",
        "<title>{}</title>".format(safe_title.replace("&", "&amp;").replace("<", "&lt;")),
        template,
        count=1,
        flags=re.DOTALL,
    )
    updated = re.sub(
        r"serverURL\s*:\s*['\"][^'\"]*['\"]",
        "serverURL: ''",
        updated,
        count=1,
    )
    if "id=\"sysoutdiv\"" not in updated and "id='sysoutdiv'" not in updated:
        updated = updated.replace(
            "</body>",
            "<pre id=\"sysoutdiv\" style=\"display:none\"></pre></body>",
            1,
        )
    return updated


def _write_manifest(
    output: Path,
    project: SourceProject,
    toolchain: SwingJSToolchain,
    *,
    title: str,
    entry_template: str,
    generated_js: str,
    generated_js_sha256: str,
    notes: List[str],
) -> Dict[str, Any]:
    artifact_id = uuid.uuid4().hex
    evidence_rel = "evidence/build.json"
    generated_files = sorted(
        {
            "index.html",
            "manifest.json",
            OWNERSHIP_MARKER_FILENAME,
            "swingjs/swingjs2.js",
            generated_js,
            evidence_rel,
        }
    )
    compatibility = {
        "status": "supported_with_workarounds" if notes else "supported",
        "summary": (
            "Java 8 Swing source was transpiled to JavaScript with the pinned "
            "Java2Script compiler. Runtime behavior was not assumed; use "
            "`provikom verify-swingjs` for browser evidence."
        ),
        "confidence_score": 0.7,
        "verified_capabilities": [
            "Java source compiled with --release 8",
            "Generated JavaScript contains the selected class",
            "Pinned SwingJS runtime and Java2Script compiler hashes verified",
        ],
        "assumptions_and_risks": list(notes),
        "blockers": [],
        "workarounds_needed": list(project.warnings),
        "remediation_steps": [],
    }
    manifest: Dict[str, Any] = {
        "schema_version": "1.1",
        "provikom_converter_version": __version__,
        "generated_at": _utc_now(),
        "backend": "swingjs",
        "entry_point": "index.html",
        "game": {
            "title": title,
            "main_class": project.main_class,
            "has_audio": project.has_audio,
            "java_major_version": 52,
            "entry_point_source": "source_scan",
        },
        "source_project": {
            "name": project.root.name,
            "main_class": project.main_class,
            "source_sha256": project.source_sha256,
            "source_file_count": project.source_file_count,
            "files": project.file_records(),
            "generated_js": generated_js,
            "generated_js_sha256": generated_js_sha256,
            "entry_template": entry_template,
        },
        "runtime": {
            "name": "SwingJS / Java2Script",
            "version": pins.SWINGJS_RUNTIME_VERSION,
            "compiler_version": pins.JAVA2SCRIPT_COMPILER_VERSION,
            "offline_capable": True,
            "license_review_required": True,
        },
        "toolchain": {
            "jdk_version": pins.JDK_VERSION,
            "jdk_archive_sha256": pins.JDK_ARCHIVE_SHA256,
            "eclipse_version": pins.ECLIPSE_VERSION,
            "eclipse_release": pins.ECLIPSE_RELEASE,
            "eclipse_archive_sha256": pins.ECLIPSE_ARCHIVE_SHA256,
            "java2script_commit": pins.JAVA2SCRIPT_COMMIT,
            "java2script_compiler_sha256": pins.JAVA2SCRIPT_COMPILER_SHA256,
            "swingjs_runtime_sha256": pins.SWINGJS_RUNTIME_SHA256,
            "toolchain_manifest_sha256": pins.TOOLCHAIN_MANIFEST_SHA256,
            "managed": toolchain.managed,
        },
        "paths": {
            "entry": "index.html",
            "generated_js": generated_js,
            "web_root": "/",
            "virtual_mount_root": "/",
        },
        "compatibility": compatibility,
        "lifecycle": built_artifact_lifecycle(),
        "generated_files": generated_files,
        "notes": [
            "Source-backed SwingJS artifact. Do not publish the bundled runtime "
            "until licensing and notice obligations are resolved."
        ]
        + list(project.warnings)
        + list(notes),
        "ownership": {
            "owner": OWNERSHIP_OWNER,
            "marker": OWNERSHIP_MARKER_FILENAME,
            "artifact_id": artifact_id,
        },
    }
    manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
    (output / "manifest.json").write_bytes(manifest_bytes)
    if not refresh_ownership_marker(output):
        raise SwingJSBuildError("Could not write the artifact ownership marker.")
    return manifest


def _evidence(
    project: SourceProject,
    toolchain: SwingJSToolchain,
    *,
    title: str,
    entry_template: str,
    generated_js: str,
    generated_js_sha256: str,
    artifact_files: int,
    artifact_bytes: int,
) -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "built_at": _utc_now(),
        "backend": "swingjs",
        "title": title,
        "main_class": project.main_class,
        "source_sha256": project.source_sha256,
        "source_file_count": project.source_file_count,
        "entry_template": entry_template,
        "generated_js": generated_js,
        "generated_js_sha256": generated_js_sha256,
        "artifact_file_count": artifact_files,
        "artifact_size_bytes": artifact_bytes,
        "toolchain": {
            "jdk_version": pins.JDK_VERSION,
            "eclipse_version": pins.ECLIPSE_VERSION,
            "java2script_commit": pins.JAVA2SCRIPT_COMMIT,
            "java2script_compiler_version": pins.JAVA2SCRIPT_COMPILER_VERSION,
            "swingjs_runtime_version": pins.SWINGJS_RUNTIME_VERSION,
            "swingjs_runtime_sha256": pins.SWINGJS_RUNTIME_SHA256,
            "managed": toolchain.managed,
        },
    }


def build_source_project(
    source_directory: Path,
    output_directory: Path,
    *,
    title: Optional[str] = None,
    main_class: Optional[str] = None,
    force_overwrite: bool = False,
    toolchain_dir: Optional[Path] = None,
    java_home: Optional[Path] = None,
    eclipse_home: Optional[Path] = None,
    site_zip: Optional[Path] = None,
) -> BuildResult:
    """Transpile and package a supported Java 8 Swing source project."""
    try:
        project = inspect_source_project(source_directory, main_class=main_class)
    except SourceProjectError as exc:
        raise SwingJSBuildError(str(exc)) from exc
    try:
        toolchain = resolve_toolchain(
            toolchain_dir=toolchain_dir,
            java_home=java_home,
            eclipse_home=eclipse_home,
            site_zip=site_zip,
        )
    except SwingJSToolchainError as exc:
        raise SwingJSBuildError(str(exc)) from exc

    game_title = title or project.root.name.replace("_", " ").replace("-", " ").title()
    output = Path(output_directory).expanduser().resolve(strict=False)
    with tempfile.TemporaryDirectory(prefix="provikom-swingjs-work-") as work_tmp:
        work = Path(work_tmp)
        work_project = work / _safe_name(project.root.name)
        _copy_project(project, work_project)
        _write_eclipse_metadata(project, work_project)
        site = work_project / "site"
        _extract_runtime(toolchain, site, work / "runtime-extract.log")
        _compile_sources(project, toolchain, work)
        _build_plugin(toolchain, work)
        eclipse_log = _run_eclipse_build(
            toolchain, work, work / "eclipse-workspace", work_project
        )
        _normalize_generated_output(site)
        entry_path, js_path = _find_generated_entry(site, project.main_class)
        generated_js = js_path.relative_to(site).as_posix()
        entry_template = entry_path.relative_to(site).as_posix()

        with atomic_source_output_directory(
            project.root, output, force_overwrite=force_overwrite
        ) as artifact:
            for item in site.iterdir():
                destination = artifact / item.name
                if item.is_dir():
                    shutil.copytree(item, destination, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, destination)
            index_template = entry_path.read_text(encoding="utf-8")
            (artifact / "index.html").write_text(
                _prepare_index(index_template, game_title), encoding="utf-8"
            )
            evidence_dir = artifact / "evidence"
            evidence_dir.mkdir(exist_ok=True)
            shutil.copy2(eclipse_log, evidence_dir / "eclipse.log")
            for log_name in ("javac-sources.log", "javac-plugin.log", "jar-plugin.log", "runtime-extract.log"):
                source_log = work / log_name
                if source_log.is_file():
                    shutil.copy2(source_log, evidence_dir / log_name)
            generated_js_sha256 = _sha256_file(artifact / generated_js)
            files = [path for path in artifact.rglob("*") if path.is_file()]
            evidence = _evidence(
                project,
                toolchain,
                title=game_title,
                entry_template=entry_template,
                generated_js=generated_js,
                generated_js_sha256=generated_js_sha256,
                artifact_files=len(files) + 3,
                artifact_bytes=sum(path.stat().st_size for path in files),
            )
            (evidence_dir / "build.json").write_text(
                json.dumps(evidence, indent=2), encoding="utf-8"
            )
            notes = []
            if project.has_audio:
                notes.append("Source imports audio APIs; browser audio is not verified.")
            _write_manifest(
                artifact,
                project,
                toolchain,
                title=game_title,
                entry_template=entry_template,
                generated_js=generated_js,
                generated_js_sha256=generated_js_sha256,
                notes=notes,
            )

    return BuildResult(
        backend_id="swingjs",
        output_directory=str(output),
        entry_html=str(output / "index.html"),
        game_jar_name="",
        game_title=game_title,
        runtime_version=8,
        runtime_label="SwingJS / Java2Script {}".format(pins.SWINGJS_RUNTIME_VERSION),
        is_experimental=False,
        generated_files=["index.html", "manifest.json", generated_js],
        manifest_path=str(output / "manifest.json"),
        metadata={
            "source_project": {
                "root": str(project.root),
                "main_class": project.main_class,
                "source_sha256": project.source_sha256,
                "source_file_count": project.source_file_count,
            },
            "game": {"title": game_title, "main_class": project.main_class},
            "generated_js": generated_js,
            "entry_template": entry_template,
            "compatibility": {
                "status": "supported_with_workarounds" if notes or project.warnings else "supported",
                "summary": "Source-backed Java2Script artifact; run verify-swingjs for runtime evidence.",
            },
            "notes": list(project.warnings) + notes,
        },
    )
