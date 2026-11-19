#!/usr/bin/env python3
"""Download and verify the pinned SwingJS/Java2Script feasibility toolchain.

The toolchain is installed under build/ by default and is never committed.
JDK and Eclipse archives are checked against pinned SHA-256 values. The
Java2Script checkout is pinned to a full Git commit, and the compiler plug-in
and runtime ZIP are checked against their own SHA-256 values.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = Path(__file__).with_name("toolchain_manifest.json")
DEFAULT_DEST = ROOT / "build" / "swingjs-toolchain"
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class SetupError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_file(path: Path, expected: str, label: str) -> None:
    if not path.is_file():
        raise SetupError("{} not found: {}".format(label, path))
    actual = _sha256(path)
    if actual != expected:
        raise SetupError(
            "{} checksum mismatch for {}\n  expected: {}\n  actual:   {}".format(
                label, path, expected, actual
            )
        )


def _run(command: List[str], *, cwd: Optional[Path] = None, timeout: int = 300) -> subprocess.CompletedProcess:
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise SetupError(
            "Command failed ({}): {}\n{}".format(
                result.returncode, " ".join(command), result.stdout + result.stderr
            )
        )
    return result


def _download(url: str, target: Path, expected_sha: str, expected_size: int, label: str) -> None:
    if target.is_file():
        if target.stat().st_size == expected_size and _sha256(target) == expected_sha:
            print("    {}: cached and verified".format(label))
            return
        print("    {}: cached file failed verification; downloading again".format(label))
        target.unlink()

    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    if partial.exists():
        partial.unlink()
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "provikom-converter-toolchain/1.0"},
    )
    print("    {}: downloading {}".format(label, url))
    digest = hashlib.sha256()
    size = 0
    try:
        with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        if size != expected_size:
            raise SetupError(
                "{} size mismatch: expected {} bytes, received {}".format(
                    label, expected_size, size
                )
            )
        actual = digest.hexdigest()
        if actual != expected_sha:
            raise SetupError(
                "{} checksum mismatch\n  expected: {}\n  actual:   {}".format(
                    label, expected_sha, actual
                )
            )
        partial.replace(target)
    except Exception:
        if partial.exists():
            partial.unlink()
        raise
    print("    {}: verified {}".format(label, expected_sha))


def _extract(
    archive: Path,
    destination: Path,
    required: List[Path],
    label: str,
    expected_sha256: str,
) -> None:
    stamp = destination / ".provikom-archive-sha256"
    if (
        destination.is_dir()
        and stamp.is_file()
        and stamp.read_text(encoding="utf-8").strip() == expected_sha256
        and all((destination / item).is_file() for item in required)
    ):
        print("    {}: already extracted from verified archive".format(label))
        return
    if destination.exists():
        shutil.rmtree(str(destination))
    temporary = destination.with_name(destination.name + ".extract")
    if temporary.exists():
        shutil.rmtree(str(temporary))
    temporary.mkdir(parents=True)
    print("    {}: extracting".format(label))
    try:
        _run(
            [
                "tar",
                "-xzf",
                str(archive),
                "--strip-components=1",
                "--no-same-owner",
                "-C",
                str(temporary),
            ],
            timeout=600,
        )
        missing = [str(item) for item in required if not (temporary / item).is_file()]
        if missing:
            raise SetupError("{} archive is missing: {}".format(label, ", ".join(missing)))
        (temporary / stamp.name).write_text(expected_sha256 + "\n", encoding="utf-8")
        temporary.rename(destination)
    except Exception:
        if temporary.exists():
            shutil.rmtree(str(temporary))
        raise


def _copy_verified(source: Path, target: Path, expected_sha: str, label: str) -> None:
    _verify_file(source, expected_sha, label)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(source), str(target))
    _verify_file(target, expected_sha, label + " installed copy")


def _checkout_java2script(destination: Path, data: Dict[str, object]) -> None:
    repository = str(data["repository"])
    commit = str(data["commit"])
    if not COMMIT_RE.match(commit):
        raise SetupError("Java2Script commit must be a full 40-character SHA-1: {}".format(commit))
    compiler = destination / str(data["compiler_jar"])
    runtime = destination / str(data["runtime_zip"])
    license_file = destination / "LICENSE.txt"
    if (
        destination.is_dir()
        and (destination / ".git").is_dir()
        and compiler.is_file()
        and runtime.is_file()
        and license_file.is_file()
    ):
        current = _run(["git", "-C", str(destination), "rev-parse", "HEAD"]).stdout.strip()
        if current == commit:
            _verify_file(compiler, str(data["compiler_jar_sha256"]), "Java2Script compiler")
            _verify_file(runtime, str(data["runtime_zip_sha256"]), "SwingJS runtime")
            _verify_file(license_file, str(data["license_sha256"]), "Java2Script license")
            print("    Java2Script: already checked out at {}".format(commit[:12]))
            return
    if destination.exists():
        shutil.rmtree(str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    print("    Java2Script: fetching {} from {}".format(commit[:12], repository))
    _run(["git", "init", "-q", str(destination)])
    _run(["git", "-C", str(destination), "remote", "add", "origin", repository])
    _run(["git", "-C", str(destination), "fetch", "-q", "--depth", "1", "origin", commit], timeout=600)
    _run(
        [
            "git",
            "-C",
            str(destination),
            "sparse-checkout",
            "init",
            "--cone",
        ]
    )
    _run(
        [
            "git",
            "-C",
            str(destination),
            "sparse-checkout",
            "set",
            "sources/net.sf.j2s.core/dist/swingjs",
        ]
    )
    _run(["git", "-C", str(destination), "checkout", "-q", "--detach", "FETCH_HEAD"])
    actual = _run(["git", "-C", str(destination), "rev-parse", "HEAD"]).stdout.strip()
    if actual != commit:
        raise SetupError(
            "Java2Script checkout mismatch: expected {}, got {}".format(commit, actual)
        )
    license_data = subprocess.run(
        ["git", "-C", str(destination), "show", "HEAD:LICENSE.txt"],
        check=True,
        capture_output=True,
    ).stdout
    license_file.write_bytes(license_data)
    _verify_file(compiler, str(data["compiler_jar_sha256"]), "Java2Script compiler")
    _verify_file(runtime, str(data["runtime_zip_sha256"]), "SwingJS runtime")
    _verify_file(license_file, str(data["license_sha256"]), "Java2Script license")


def _java_version(java: Path) -> str:
    result = _run([str(java), "-version"], timeout=60)
    text = (result.stdout or "") + (result.stderr or "")
    return text.strip().splitlines()[0] if text.strip() else ""


def setup(manifest_path: Path, destination: Path, cache_dir: Optional[Path]) -> Dict[str, object]:
    manifest_data = manifest_path.read_bytes()
    manifest = json.loads(manifest_data)
    manifest_sha = hashlib.sha256(manifest_data).hexdigest()
    jdk = manifest["jdk"]
    eclipse = manifest["eclipse"]
    java2script = manifest["java2script"]

    destination = destination.resolve()
    downloads = destination / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    print("==> Toolchain destination: {}".format(destination))
    print("==> Verifying pinned archives")
    for key, data in (("JDK", jdk), ("Eclipse", eclipse)):
        target = downloads / data["archive_name"]
        if cache_dir is not None:
            cached = cache_dir / data["archive_name"]
            if cached.is_file() and _sha256(cached) == data["sha256"]:
                if not target.is_file() or _sha256(target) != data["sha256"]:
                    shutil.copy2(str(cached), str(target))
        _download(
            str(data["url"]),
            target,
            str(data["sha256"]),
            int(data["archive_size_bytes"]),
            key,
        )

    print("==> Extracting JDK and Eclipse")
    jdk_home = destination / "jdk"
    eclipse_home = destination / "eclipse"
    _extract(
        downloads / jdk["archive_name"],
        jdk_home,
        [Path("bin") / "java", Path("bin") / "javac"],
        "JDK",
        str(jdk["sha256"]),
    )
    _extract(
        downloads / eclipse["archive_name"],
        eclipse_home,
        [Path("eclipse"), Path(".eclipseproduct")],
        "Eclipse",
        str(eclipse["sha256"]),
    )

    print("==> Fetching pinned Java2Script compiler and runtime")
    java2script_home = destination / "java2script"
    _checkout_java2script(java2script_home, java2script)
    compiler = java2script_home / str(java2script["compiler_jar"])
    runtime = java2script_home / str(java2script["runtime_zip"])

    print("==> Installing Java2Script Eclipse plug-in")
    installed_compiler = eclipse_home / "dropins" / "j2s.core.jar"
    _copy_verified(compiler, installed_compiler, str(java2script["compiler_jar_sha256"]), "Java2Script compiler")

    product = eclipse_home / ".eclipseproduct"
    product_text = product.read_text(encoding="utf-8", errors="replace").strip()
    java_version = _java_version(jdk_home / "bin" / "java")
    record = {
        "schema_version": "1.0",
        "installed_at": int(time.time()),
        "manifest": str(manifest_path),
        "manifest_sha256": manifest_sha,
        "paths": {
            "toolchain": str(destination),
            "java_home": str(jdk_home),
            "eclipse_home": str(eclipse_home),
            "java2script_home": str(java2script_home),
            "swingjs_site_zip": str(runtime),
        },
        "jdk": {
            "version": str(jdk["version"]),
            "archive": str(downloads / str(jdk["archive_name"])),
            "archive_sha256": str(jdk["sha256"]),
            "java_version": java_version,
        },
        "eclipse": {
            "version": str(eclipse["version"]),
            "release": str(eclipse["release"]),
            "archive": str(downloads / str(eclipse["archive_name"])),
            "archive_sha256": str(eclipse["sha256"]),
            "sha512": str(eclipse["sha512"]),
            "product": product_text,
        },
        "java2script": {
            "repository": str(java2script["repository"]),
            "commit": str(java2script["commit"]),
            "compiler_version": str(java2script["compiler_version"]),
            "runtime_version": str(java2script["runtime_version"]),
            "compiler_jar": str(compiler),
            "compiler_jar_sha256": str(java2script["compiler_jar_sha256"]),
            "installed_compiler_jar": str(installed_compiler),
            "runtime_zip": str(runtime),
            "runtime_zip_sha256": str(java2script["runtime_zip_sha256"]),
            "license_sha256": str(java2script["license_sha256"]),
        },
    }
    record_path = destination / "toolchain.json"
    record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("")
    print("Toolchain ready: {}".format(record_path))
    print("  JAVA_HOME:            {}".format(jdk_home))
    print("  ECLIPSE_HOME:         {}".format(eclipse_home))
    print("  SWINGJS_SITE_ZIP:     {}".format(runtime))
    return record


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", default=str(DEFAULT_DEST), help="Install destination (default: build/swingjs-toolchain).")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Pinned toolchain manifest.")
    parser.add_argument("--cache-dir", help="Optional directory containing verified archives by archive filename.")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        setup(
            Path(args.manifest).expanduser().resolve(),
            Path(args.dest).expanduser().resolve(),
            Path(args.cache_dir).expanduser().resolve() if args.cache_dir else None,
        )
    except (SetupError, OSError, subprocess.SubprocessError) as exc:
        print("TOOLCHAIN SETUP FAILED: {}".format(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
