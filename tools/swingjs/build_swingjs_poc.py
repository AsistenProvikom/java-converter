#!/usr/bin/env python3
"""Build the Milestone 2C.0 SwingPoc artifact with headless Eclipse + Java2Script.

The Java2Script compiler is an Eclipse JDT compilation participant, not a
standalone CLI. This script builds a tiny Eclipse application that imports the
example project and triggers a full JDT build, then packages the generated
SwingJS site and a CheerpJ-comparable POC JAR.

Required external inputs are intentionally not committed:

  * JDK 17+ (Eclipse 2024-03 requires Java 17)
  * Eclipse IDE for Java Developers 2024-03 (or compatible)
  * BobHanson/java2script's SwingJS-site.zip

Use --java-home, --eclipse-home, and --swingjs-site-zip (or the matching
PROVIKOM_* environment variables). See docs/MILESTONE_2C_FEASIBILITY.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROJECT = ROOT / "examples" / "swing-poc"
DEFAULT_OUTPUT = ROOT / "build" / "swingjs-poc"
PLUGIN_SOURCE = Path(__file__).resolve().parent / "headless-builder"
PLUGIN_ID = "provikom.j2s.builder"
PLUGIN_JAR = PLUGIN_ID + ".jar"


class BuildError(RuntimeError):
    pass


def _run(
    command: List[str],
    *,
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: int = 240,
    log_path: Optional[Path] = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        env=merged,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = (result.stdout or "") + (result.stderr or "")
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(output, encoding="utf-8")
    if check and result.returncode != 0:
        raise BuildError(
            "Command failed ({}): {}\n{}".format(result.returncode, " ".join(command), output[-4000:])
        )
    return result


def _java_major(java: Path) -> int:
    result = _run([str(java), "-version"], check=False)
    text = (result.stdout or "") + (result.stderr or "")
    match = re.search(r'version "(?:1\.)?(\d+)', text)
    if not match:
        raise BuildError("Could not parse Java version from: " + text)
    return int(match.group(1))


def _find_java_home(explicit: Optional[str]) -> Path:
    candidate = explicit or os.environ.get("PROVIKOM_JAVA_HOME") or os.environ.get("JAVA_HOME")
    if not candidate:
        raise BuildError(
            "Set --java-home or PROVIKOM_JAVA_HOME to a JDK 17+ installation."
        )
    java_home = Path(candidate).expanduser().resolve()
    if not (java_home / "bin" / "java").is_file():
        raise BuildError("JDK not found at {}".format(java_home))
    major = _java_major(java_home / "bin" / "java")
    if major < 17:
        raise BuildError(
            "Eclipse 2024-03 requires Java 17+; {} is Java {}".format(java_home, major)
        )
    return java_home


def _find_eclipse(explicit: Optional[str]) -> Path:
    candidate = explicit or os.environ.get("PROVIKOM_ECLIPSE_HOME")
    if candidate:
        eclipse_home = Path(candidate).expanduser().resolve()
        for name in ("eclipse", "eclipsec"):
            if (eclipse_home / name).is_file():
                return eclipse_home
        raise BuildError("No eclipse or eclipsec launcher in {}".format(eclipse_home))
    raise BuildError(
        "Set --eclipse-home or PROVIKOM_ECLIPSE_HOME to an Eclipse installation."
    )


def _find_site_zip(explicit: Optional[str]) -> Path:
    candidate = explicit or os.environ.get("PROVIKOM_SWINGJS_SITE_ZIP")
    if not candidate:
        raise BuildError(
            "Set --swingjs-site-zip or PROVIKOM_SWINGJS_SITE_ZIP to "
            "sources/net.sf.j2s.core/dist/swingjs/SwingJS-site.zip."
        )
    site_zip = Path(candidate).expanduser().resolve()
    if not site_zip.is_file():
        raise BuildError("SwingJS site zip not found: {}".format(site_zip))
    return site_zip


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_project(project: Path, destination: Path) -> None:
    ignore = shutil.ignore_patterns("bin", "site", "classes", "test-classes", "*.class", "__pycache__")
    shutil.copytree(str(project), str(destination), ignore=ignore)


def _build_plugin(java_home: Path, eclipse_home: Path, toolchain_dir: Path) -> Path:
    classes = toolchain_dir / "plugin-classes"
    if classes.exists():
        shutil.rmtree(str(classes))
    classes.mkdir(parents=True)
    classpath = os.pathsep.join(str(p) for p in sorted((eclipse_home / "plugins").glob("*.jar")))
    source = PLUGIN_SOURCE / "provikom" / "j2s" / "builder" / "ImportAndBuildApplication.java"
    _run(
        [
            str(java_home / "bin" / "javac"),
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
        log_path=toolchain_dir / "javac-plugin.log",
    )
    shutil.copy2(str(PLUGIN_SOURCE / "plugin.xml"), str(classes / "plugin.xml"))
    manifest_dir = classes / "META-INF"
    manifest_dir.mkdir()
    shutil.copy2(str(PLUGIN_SOURCE / "META-INF" / "MANIFEST.MF"), str(manifest_dir / "MANIFEST.MF"))
    jar_path = toolchain_dir / PLUGIN_JAR
    _run(
        [
            str(java_home / "bin" / "jar"),
            "cfm",
            str(jar_path),
            str(manifest_dir / "MANIFEST.MF"),
            "-C",
            str(classes),
            ".",
        ],
        log_path=toolchain_dir / "jar-plugin.log",
    )
    return jar_path


def _install_plugin(plugin_jar: Path, eclipse_home: Path) -> Path:
    dropins = eclipse_home / "dropins"
    try:
        dropins.mkdir(parents=True, exist_ok=True)
        target = dropins / PLUGIN_JAR
        shutil.copy2(str(plugin_jar), str(target))
    except OSError as exc:
        raise BuildError(
            "Could not install the headless builder plug-in into {}/dropins: {}".format(
                eclipse_home, exc
            )
        )
    return target


def _compile_poc(java_home: Path, project: Path, output_dir: Path) -> Tuple[Path, Path]:
    classes = output_dir / "classes"
    test_classes = output_dir / "test-classes"
    if classes.exists():
        shutil.rmtree(str(classes))
    if test_classes.exists():
        shutil.rmtree(str(test_classes))
    classes.mkdir(parents=True)
    test_classes.mkdir(parents=True)

    src_files = sorted(str(p) for p in (project / "src").rglob("*.java"))
    _run(
        [
            str(java_home / "bin" / "javac"),
            "--release",
            "8",
            "-d",
            str(classes),
        ]
        + src_files,
        log_path=output_dir / "javac-poc.log",
    )
    jar_path = output_dir / "SwingPoc.jar"
    _run(
        [
            str(java_home / "bin" / "jar"),
            "--create",
            "--file",
            str(jar_path),
            "--main-class",
            "poc.SwingPoc",
            "-C",
            str(classes),
            ".",
        ],
        log_path=output_dir / "jar-poc.log",
    )

    test_files = sorted(str(p) for p in (project / "test").rglob("*.java"))
    _run(
        [
            str(java_home / "bin" / "javac"),
            "--release",
            "8",
            "-cp",
            str(classes),
            "-d",
            str(test_classes),
        ]
        + test_files,
        log_path=output_dir / "javac-desktop-test.log",
    )
    return jar_path, test_classes


def _start_xvfb(xvfb: Optional[str]) -> Tuple[Optional[subprocess.Popen], Optional[str], Optional[str]]:
    if os.environ.get("DISPLAY"):
        return None, None, os.environ.get("DISPLAY")
    binary = xvfb or os.environ.get("PROVIKOM_XVFB") or shutil.which("Xvfb")
    if not binary:
        return None, None, None
    binary_path = Path(binary).expanduser().resolve()
    if not binary_path.is_file():
        return None, None, None
    for display_num in range(99, 120):
        display = ":{}".format(display_num)
        lock = Path("/tmp/.X{}-lock".format(display_num))
        if lock.exists():
            continue
        process = subprocess.Popen(
            [str(binary_path), display, "-screen", "0", "1280x900x24", "-nolisten", "tcp"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        socket_path = Path("/tmp/.X11-unix/X{}".format(display_num))
        deadline = time.time() + 5
        while time.time() < deadline:
            if process.poll() is not None:
                break
            if socket_path.exists():
                return process, display, display
            time.sleep(0.05)
        if process.poll() is None:
            process.terminate()
    return None, None, None


def _run_desktop_test(
    java_home: Path,
    output_dir: Path,
    classes: Path,
    test_classes: Path,
    xvfb: Optional[str],
    require_desktop: bool,
) -> Dict[str, object]:
    process, display, effective_display = _start_xvfb(xvfb)
    if not effective_display:
        record = {
            "status": "skipped",
            "reason": "No DISPLAY and no Xvfb available.",
        }
        if require_desktop:
            raise BuildError("Desktop verification was required but no display/Xvfb is available.")
        return record
    try:
        env = {"DISPLAY": effective_display}
        screenshot = output_dir / "desktop-poc.png"
        result = _run(
            [
                str(java_home / "bin" / "java"),
                "-cp",
                os.pathsep.join([str(test_classes), str(classes)]),
                "poc.DesktopSmokeTest",
                str(screenshot),
            ],
            env=env,
            log_path=output_dir / "desktop-smoke.log",
            timeout=120,
        )
        output = (result.stdout or "") + (result.stderr or "")
        if "DESKTOP_SMOKE_OK" not in output:
            raise BuildError("Desktop smoke test did not report success:\n" + output[-4000:])
        return {
            "status": "passed",
            "display": effective_display,
            "screenshot": str(screenshot.relative_to(ROOT)) if screenshot.is_relative_to(ROOT) else str(screenshot),
            "log": "build/swingjs-poc/desktop-smoke.log",
        }
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


def _run_eclipse_build(
    java_home: Path,
    eclipse_home: Path,
    workspace: Path,
    project: Path,
    output_dir: Path,
) -> str:
    launcher = eclipse_home / "eclipse"
    if not launcher.is_file():
        launcher = eclipse_home / "eclipsec"
    log_path = output_dir / "eclipse.log"
    result = _run(
        [
            str(launcher),
            "-nosplash",
            "-clean",
            "-consoleLog",
            "-data",
            str(workspace),
            "-application",
            "{}.application".format(PLUGIN_ID),
            "-vm",
            str(java_home / "bin" / "java"),
            "-vmargs",
            "-Dprovikom.project={}".format(project),
        ],
        timeout=240,
        log_path=log_path,
        check=False,
    )
    output = (result.stdout or "") + (result.stderr or "")
    if "PROVIKOM_BUILD_OK" not in output:
        raise BuildError(
            "Headless Eclipse Java2Script build failed (exit {}). See {}:\n{}".format(
                result.returncode, log_path, output[-5000:]
            )
        )
    return output


def _record_toolchain(
    java_home: Path,
    eclipse_home: Path,
    site_zip: Path,
    project: Path,
    output_dir: Path,
    jar_path: Path,
    desktop: Dict[str, object],
) -> Dict[str, object]:
    site_dir = output_dir / "site"
    files = [p for p in site_dir.rglob("*") if p.is_file()]
    java_version = _run([str(java_home / "bin" / "java"), "-version"], check=False)
    java_text = ((java_version.stdout or "") + (java_version.stderr or "")).strip().splitlines()
    eclipse_text = ""
    about = eclipse_home / ".eclipseproduct"
    if about.is_file():
        eclipse_text = about.read_text(encoding="utf-8", errors="replace").strip()
    data = {
        "generated_at": int(time.time()),
        "java_home": str(java_home),
        "java_version": java_text[0] if java_text else "",
        "eclipse_home": str(eclipse_home),
        "eclipse_product": eclipse_text,
        "swingjs_site_zip": str(site_zip),
        "swingjs_site_zip_sha256": _sha256(site_zip),
        "project_source_sha256": hashlib.sha256(
            b"".join(p.read_bytes() for p in sorted((project / "src").rglob("*.java")))
        ).hexdigest(),
        "poc_jar": str(jar_path),
        "poc_jar_size_bytes": jar_path.stat().st_size,
        "poc_jar_sha256": _sha256(jar_path),
        "artifact_file_count": len(files),
        "artifact_size_bytes": sum(p.stat().st_size for p in files),
        "desktop_verification": desktop,
        "entry_html": "site/poc_SwingPoc.html",
        "generated_js": "site/swingjs/j2s/poc/SwingPoc.js",
    }
    (output_dir / "toolchain.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def build(args: argparse.Namespace) -> Dict[str, object]:
    project = Path(args.project_dir).expanduser().resolve()
    if not project.is_dir():
        raise BuildError("Project directory not found: {}".format(project))
    output_dir = Path(args.output_dir).expanduser().resolve()
    java_home = _find_java_home(args.java_home)
    eclipse_home = _find_eclipse(args.eclipse_home)
    site_zip = _find_site_zip(args.swingjs_site_zip)

    output_dir.mkdir(parents=True, exist_ok=True)
    toolchain_dir = output_dir / "toolchain"
    toolchain_dir.mkdir(parents=True, exist_ok=True)
    work_root = output_dir / "work"
    if work_root.exists():
        shutil.rmtree(str(work_root))
    work_root.mkdir(parents=True)
    work_project = work_root / project.name
    workspace = work_root / "eclipse-workspace"

    print("==> Building headless Java2Script builder plug-in")
    plugin_jar = _build_plugin(java_home, eclipse_home, toolchain_dir)
    _install_plugin(plugin_jar, eclipse_home)

    print("==> Preparing SwingPoc project and SwingJS runtime")
    _copy_project(project, work_project)
    site_dir = work_project / "site"
    site_dir.mkdir()
    _run(
        ["unzip", "-q", "-o", str(site_zip), "-d", str(site_dir)],
        log_path=output_dir / "unzip-site.log",
    )

    print("==> Compiling SwingPoc and desktop smoke test")
    jar_path, test_classes = _compile_poc(java_home, project, output_dir)
    classes = output_dir / "classes"

    print("==> Verifying the desktop application")
    desktop = _run_desktop_test(
        java_home,
        output_dir,
        classes,
        test_classes,
        args.xvfb,
        args.require_desktop,
    )
    print("    desktop verification: {}".format(desktop["status"]))

    print("==> Running headless Eclipse Java2Script build")
    eclipse_output = _run_eclipse_build(java_home, eclipse_home, workspace, work_project, output_dir)
    js_path = work_project / "site" / "swingjs" / "j2s" / "poc" / "SwingPoc.js"
    html_path = work_project / "site" / "poc_SwingPoc.html"
    if not js_path.is_file() or not html_path.is_file():
        raise BuildError(
            "Java2Script reported success but expected outputs are missing: {} / {}".format(
                js_path, html_path
            )
        )
    if "J2S SwingJS plugin processed" not in eclipse_output:
        raise BuildError("Eclipse log did not show a Java2Script transpile result.")

    print("==> Publishing artifact")
    final_site = output_dir / "site"
    if final_site.exists():
        shutil.rmtree(str(final_site))
    shutil.copytree(str(work_project / "site"), str(final_site))

    record = _record_toolchain(
        java_home, eclipse_home, site_zip, project, output_dir, jar_path, desktop
    )
    print("")
    print("Artifact:     {}".format(output_dir / "site"))
    print("Entry HTML:   {}".format(output_dir / "site" / "poc_SwingPoc.html"))
    print("POC JAR:      {}".format(output_dir / "SwingPoc.jar"))
    print("Artifact size: {:,} bytes in {:,} files".format(
        record["artifact_size_bytes"], record["artifact_file_count"]
    ))
    print("Next: python3 tools/swingjs/verify_swingjs_poc.py --artifact-dir {}".format(output_dir))
    return record


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", default=str(DEFAULT_PROJECT))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--java-home")
    parser.add_argument("--eclipse-home")
    parser.add_argument("--swingjs-site-zip")
    parser.add_argument(
        "--xvfb",
        help="Path to Xvfb for desktop verification (or set PROVIKOM_XVFB).",
    )
    parser.add_argument(
        "--require-desktop",
        action="store_true",
        help="Fail instead of skipping when no display/Xvfb is available.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        build(args)
    except (BuildError, subprocess.TimeoutExpired) as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
