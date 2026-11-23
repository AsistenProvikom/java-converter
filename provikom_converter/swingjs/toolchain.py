"""Resolve and verify the pinned SwingJS/Java2Script toolchain."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Union

from provikom_converter.swingjs import pins


class SwingJSToolchainError(RuntimeError):
    """Raised when the pinned SwingJS toolchain is missing or unverified."""


@dataclass(frozen=True)
class SwingJSToolchain:
    java_home: Path
    eclipse_home: Path
    site_zip: Path
    compiler_jar: Path
    record: Dict[str, Any]
    managed: bool

    @property
    def java(self) -> Path:
        return self.java_home / "bin" / "java"

    @property
    def javac(self) -> Path:
        return self.java_home / "bin" / "javac"

    @property
    def eclipse_launcher(self) -> Path:
        for name in ("eclipse", "eclipsec"):
            candidate = self.eclipse_home / name
            if candidate.is_file():
                return candidate
        raise SwingJSToolchainError(
            "No Eclipse launcher found under {}".format(self.eclipse_home)
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_sha256(path: Path, expected: str, label: str) -> None:
    if not path.is_file():
        raise SwingJSToolchainError("{} is missing: {}".format(label, path))
    actual = _sha256(path)
    if actual != expected:
        raise SwingJSToolchainError(
            "{} checksum mismatch for {}\n  expected: {}\n  actual:   {}".format(
                label, path, expected, actual
            )
        )


def _load_record(directory: Path) -> Dict[str, Any]:
    path = directory / "toolchain.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SwingJSToolchainError(
            "Could not read toolchain record {}: {}".format(path, exc)
        ) from exc
    if not isinstance(data, dict):
        raise SwingJSToolchainError("Toolchain record must be a JSON object: {}".format(path))
    return data


def _java_major(java: Path) -> int:
    import subprocess

    if not java.is_file():
        raise SwingJSToolchainError("Java executable not found: {}".format(java))
    result = subprocess.run(
        [str(java), "-version"], capture_output=True, text=True, timeout=60
    )
    text = (result.stdout or "") + (result.stderr or "")
    match = re.search(r'version "(?:1\.)?(\d+)', text)
    if not match:
        raise SwingJSToolchainError("Could not parse Java version from: " + text)
    return int(match.group(1))


def _first_existing(*candidates: Optional[Union[str, Path]]) -> Optional[Path]:
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser().resolve(strict=False)
        if path.exists():
            return path
    return None


def resolve_toolchain(
    *,
    toolchain_dir: Optional[Union[str, Path]] = None,
    java_home: Optional[Union[str, Path]] = None,
    eclipse_home: Optional[Union[str, Path]] = None,
    site_zip: Optional[Union[str, Path]] = None,
) -> SwingJSToolchain:
    """Resolve the managed or explicitly supplied pinned toolchain."""
    directory = (
        toolchain_dir
        or os.environ.get("PROVIKOM_SWINGJS_TOOLCHAIN")
        or Path.cwd() / "build" / "swingjs-toolchain"
    )
    directory = Path(directory).expanduser().resolve(strict=False)
    record = _load_record(directory)
    paths = record.get("paths") if isinstance(record.get("paths"), dict) else {}
    java2script = (
        record.get("java2script")
        if isinstance(record.get("java2script"), dict)
        else {}
    )

    runtime_fallback = (
        directory
        / "java2script"
        / "sources"
        / "net.sf.j2s.core"
        / "dist"
        / "swingjs"
        / "SwingJS-site.zip"
    )
    java_home_path = _first_existing(
        java_home,
        os.environ.get("PROVIKOM_JAVA_HOME"),
        paths.get("java_home"),
        directory / "jdk",
    )
    eclipse_path = _first_existing(
        eclipse_home,
        os.environ.get("PROVIKOM_ECLIPSE_HOME"),
        paths.get("eclipse_home"),
        directory / "eclipse",
    )
    site_zip_path = _first_existing(
        site_zip,
        os.environ.get("PROVIKOM_SWINGJS_SITE_ZIP"),
        paths.get("swingjs_site_zip"),
        runtime_fallback,
    )
    compiler_path = _first_existing(
        os.environ.get("PROVIKOM_SWINGJS_COMPILER_JAR"),
        java2script.get("installed_compiler_jar"),
        eclipse_path / "dropins" / "j2s.core.jar" if eclipse_path else None,
        java2script.get("compiler_jar"),
    )

    missing = [
        label
        for label, value in (
            ("Java home", java_home_path),
            ("Eclipse home", eclipse_path),
            ("SwingJS runtime ZIP", site_zip_path),
            ("Java2Script compiler JAR", compiler_path),
        )
        if value is None
    ]
    if missing:
        raise SwingJSToolchainError(
            "Pinned SwingJS toolchain is incomplete ({}). Run "
            "python3 tools/swingjs/setup_toolchain.py or pass explicit toolchain paths.".format(
                ", ".join(missing)
            )
        )

    assert java_home_path and eclipse_path and site_zip_path and compiler_path
    major = _java_major(java_home_path / "bin" / "java")
    if major < 17:
        raise SwingJSToolchainError(
            "Eclipse 2024-03 requires Java 17+; {} is Java {}".format(
                java_home_path, major
            )
        )

    _verify_sha256(site_zip_path, pins.SWINGJS_RUNTIME_SHA256, "SwingJS runtime ZIP")
    _verify_sha256(compiler_path, pins.JAVA2SCRIPT_COMPILER_SHA256, "Java2Script compiler")
    def _inside(path: Path) -> bool:
        try:
            path.resolve().relative_to(directory)
        except ValueError:
            return False
        return True

    managed = all(_inside(path) for path in (java_home_path, eclipse_path, site_zip_path))
    return SwingJSToolchain(
        java_home=java_home_path,
        eclipse_home=eclipse_path,
        site_zip=site_zip_path,
        compiler_jar=compiler_path,
        record=record,
        managed=managed,
    )
