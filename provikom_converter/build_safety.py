"""Safe, transactional output handling for generated web artifacts.

Artifact builds may use ``--force`` to replace an existing output directory.
Deleting a user-supplied path is inherently dangerous, so every output path is
validated against the input archive before anything is removed. Builds are
written to a temporary sibling directory and published atomically; a failed
build never destroys the previous artifact.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, Iterator, Tuple, Union


OWNERSHIP_MARKER_FILENAME = ".provikom-artifact.json"
OWNERSHIP_MARKER_SCHEMA_VERSION = "1.0"
OWNERSHIP_OWNER = "provikom-converter"
SUPPORTED_BACKENDS = frozenset({"cheerpj", "teavm", "swingjs"})


class BuildPathError(ValueError):
    """Raised when an output path could destroy source data or is unsafe."""


def _resolve(path: Union[str, Path]) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _absolute_without_resolving(path: Path) -> Path:
    if path.is_absolute():
        return path
    return Path.cwd() / path


def _reject_symlink_components(path: Path, label: str) -> None:
    """Reject a symlink at any existing component of ``path``.

    The check deliberately uses absolute components without calling resolve(),
    so an output path cannot escape through a symlinked parent directory.
    """
    absolute = _absolute_without_resolving(path)
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise BuildPathError(
                f"Refusing to use {label} '{path}': path component "
                f"'{current}' is a symbolic link. Point the output at a real "
                "directory so --force cannot escape the intended location."
            )


def _reject_existing_symlink(path: Path, label: str) -> None:
    if path.is_symlink():
        raise BuildPathError(
            f"Refusing to use {label} '{path}': the path is a symbolic link. "
            "Point the output at a real directory so --force cannot escape the "
            "intended location."
        )


def _reject_path_traversal(path: Path) -> None:
    if any(part == ".." for part in path.parts):
        raise BuildPathError(
            f"Refusing to use output path '{path}': parent-directory traversal "
            "is not allowed. Pass a normalized output path instead."
        )


def validate_output_directory(
    source_jar_path: Union[str, Path],
    output_directory: Union[str, Path],
) -> Tuple[Path, Path]:
    """Validate an artifact output path against the source archive.

    Returns the resolved ``(source_jar, output_directory)`` pair. The output
    must not be the source JAR, its parent directory, or any ancestor of the
    source JAR. Filesystem roots and symlinks at any existing output path
    component are rejected.
    """
    source = _resolve(source_jar_path)
    if not source.is_file():
        raise BuildPathError(f"Input archive does not exist or is not a file: {source}")

    raw_output = Path(output_directory).expanduser()
    _reject_path_traversal(raw_output)
    # Validate the caller's raw path before resolving it. Resolving first would
    # hide symlinked path components and bypass this rejection.
    _reject_symlink_components(raw_output, "output directory")
    output = _resolve(raw_output)

    if output == Path(output.anchor):
        raise BuildPathError(
            f"Refusing to use filesystem root '{output}' as an artifact output directory."
        )

    if output == source:
        raise BuildPathError(
            f"Output directory '{output}' is the input JAR itself. Choose a separate directory."
        )

    source_dir = source.parent
    if output == source_dir:
        raise BuildPathError(
            f"Output directory '{output}' is the input JAR's parent directory. "
            "Refusing to delete or replace source files."
        )

    if output in source.parents:
        raise BuildPathError(
            f"Output directory '{output}' is an ancestor of the input JAR '{source}'. "
            "Choose a sibling or child directory that does not contain the source archive."
        )

    # Reject the case where the source archive sits inside the output directory
    # through a different spelling or symlinked parent.
    try:
        source.relative_to(output)
    except ValueError:
        pass
    else:
        raise BuildPathError(
            f"Input JAR '{source}' is inside output directory '{output}'. "
            "Refusing to replace a directory that contains the source archive."
        )

    return source, output


def _target_is_empty(directory: Path) -> bool:
    try:
        next(directory.iterdir())
    except StopIteration:
        return True
    return False


def _read_json_file(path: Path) -> Tuple[Dict, bytes]:
    if path.is_symlink() or not path.is_file():
        return {}, b""
    try:
        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return {}, b""
    return (data if isinstance(data, dict) else {}), raw


def _read_artifact_manifest(directory: Path) -> Tuple[Dict, bytes]:
    return _read_json_file(directory / "manifest.json")


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value.lower())
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_artifact_file(directory: Path, name: Any) -> Union[Path, None]:
    """Resolve a manifest path only if it stays inside the artifact directory."""
    if not isinstance(name, str) or not name:
        return None
    normalized = name.replace("\\", "/")
    relative = PurePosixPath(normalized)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".."} for part in relative.parts)
    ):
        return None
    candidate = directory.joinpath(*relative.parts)
    if candidate.is_symlink() or not candidate.is_file():
        return None
    try:
        candidate.resolve().relative_to(directory.resolve())
    except ValueError:
        return None
    return candidate


def _generated_files_are_intact(
    directory: Path, manifest: Dict, required: Iterable[str]
) -> bool:
    generated = manifest.get("generated_files")
    if not isinstance(generated, list):
        return False
    present = set()
    for name in generated:
        if _safe_artifact_file(directory, name) is None:
            return False
        present.add(name)
    return set(required).issubset(present)


def _manifest_identity_is_valid(manifest: Dict) -> bool:
    return (
        manifest.get("schema_version") in {"1.0", "1.1"}
        and isinstance(manifest.get("provikom_converter_version"), str)
        and manifest.get("backend") in SUPPORTED_BACKENDS
        and manifest.get("entry_point") == "index.html"
    )


def _manifest_game_jar_matches(directory: Path, manifest: Dict) -> bool:
    jar_name = manifest.get("jar_file")
    game = manifest.get("game")
    if not isinstance(jar_name, str) or not isinstance(game, dict):
        return False
    jar_path = _safe_artifact_file(directory, jar_name)
    if jar_path is None:
        return False
    digest = game.get("sha256")
    size = game.get("size_bytes")
    if not _is_sha256(digest) or not isinstance(size, int) or isinstance(size, bool):
        return False
    if jar_path.stat().st_size != size:
        return False
    return _sha256_file(jar_path) == digest.lower()


def _has_valid_ownership_marker(
    directory: Path, manifest: Dict, manifest_bytes: bytes
) -> bool:
    marker_path = directory / OWNERSHIP_MARKER_FILENAME
    marker, _raw = _read_json_file(marker_path)
    ownership = manifest.get("ownership")
    if not isinstance(ownership, dict):
        return False

    artifact_id = ownership.get("artifact_id")
    manifest_digest = marker.get("manifest_sha256")
    required = {
        "index.html",
        "style.css",
        "app.js",
        "manifest.json",
        OWNERSHIP_MARKER_FILENAME,
    }
    jar_name = manifest.get("jar_file")
    if isinstance(jar_name, str):
        required.add(jar_name)

    return (
        marker.get("schema_version") == OWNERSHIP_MARKER_SCHEMA_VERSION
        and marker.get("owner") == OWNERSHIP_OWNER
        and marker.get("artifact_id") == artifact_id
        and ownership.get("owner") == OWNERSHIP_OWNER
        and ownership.get("marker") == OWNERSHIP_MARKER_FILENAME
        and isinstance(artifact_id, str)
        and bool(artifact_id)
        and _is_sha256(manifest_digest)
        and hashlib.sha256(manifest_bytes).hexdigest() == manifest_digest.lower()
        and _generated_files_are_intact(directory, manifest, required)
        and _manifest_game_jar_matches(directory, manifest)
    )


def _has_valid_legacy_manifest(directory: Path, manifest: Dict) -> bool:
    """Validate artifacts built before ownership markers were introduced.

    Legacy manifests are accepted only when the manifest, staged JAR, and
    generated CheerpJ player files all agree. A manifest with plausible JSON
    fields alone is not enough to make a directory deletable.
    """
    if manifest.get("backend") != "cheerpj":
        return False
    jar_name = manifest.get("jar_file")
    if not isinstance(jar_name, str):
        return False
    required = {"index.html", "style.css", "app.js", "manifest.json", jar_name}
    if not _generated_files_are_intact(directory, manifest, required):
        return False
    if not _manifest_game_jar_matches(directory, manifest):
        return False

    index_path = directory / "index.html"
    app_path = directory / "app.js"
    try:
        index_html = index_path.read_text(encoding="utf-8")
        app_js = app_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return (
        'id="cheerpj-display"' in index_html
        and "cheerpjInit" in app_js
        and "Provikom Converter" in app_js
    )


def _is_provikom_artifact(directory: Path) -> bool:
    """Return True only when a directory proves Provikom artifact ownership."""
    manifest, manifest_bytes = _read_artifact_manifest(directory)
    if not _manifest_identity_is_valid(manifest):
        return False

    generated = manifest.get("generated_files")
    claims_ownership = "ownership" in manifest or (
        isinstance(generated, list) and OWNERSHIP_MARKER_FILENAME in generated
    )
    if claims_ownership:
        return _has_valid_ownership_marker(directory, manifest, manifest_bytes)
    return _has_valid_legacy_manifest(directory, manifest)


def refresh_ownership_marker(directory: Union[str, Path]) -> bool:
    """Rewrite the ownership marker after an intentional manifest update."""
    artifact_dir = Path(directory)
    manifest, manifest_bytes = _read_artifact_manifest(artifact_dir)
    ownership = manifest.get("ownership")
    if not isinstance(ownership, dict):
        return False
    artifact_id = ownership.get("artifact_id")
    if (
        not _manifest_identity_is_valid(manifest)
        or ownership.get("owner") != OWNERSHIP_OWNER
        or ownership.get("marker") != OWNERSHIP_MARKER_FILENAME
        or not isinstance(artifact_id, str)
        or not artifact_id
    ):
        return False

    marker_path = artifact_dir / OWNERSHIP_MARKER_FILENAME
    if marker_path.is_symlink():
        raise BuildPathError(
            f"Refusing to replace symlinked ownership marker '{marker_path}'."
        )
    marker_data = {
        "schema_version": OWNERSHIP_MARKER_SCHEMA_VERSION,
        "owner": OWNERSHIP_OWNER,
        "artifact_id": artifact_id,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
    }
    marker_path.write_text(json.dumps(marker_data, indent=2), encoding="utf-8")
    return True


def _check_replaceable_target(target_dir: Path, force_overwrite: bool) -> None:
    """Validate an existing output directory before it can be replaced.

    Empty directories and recognized Provikom artifacts may be replaced. Any
    other non-empty directory is treated as unrelated user data and is never
    deleted, even with ``--force``.
    """
    _reject_existing_symlink(target_dir, "output directory")
    if not target_dir.exists():
        return
    if not target_dir.is_dir():
        raise FileExistsError(
            f"Destination path '{target_dir}' exists and is not a directory."
        )
    if _target_is_empty(target_dir):
        return
    if not force_overwrite:
        raise FileExistsError(
            f"Destination directory '{target_dir}' already exists and is not empty. "
            "Use --force to overwrite."
        )
    if not _is_provikom_artifact(target_dir):
        raise BuildPathError(
            f"Refusing to overwrite '{target_dir}': it is non-empty and does not "
            "contain valid Provikom ownership proof. Move or remove unrelated "
            "data explicitly before using --force."
        )


def _publish(temp_dir: Path, target_dir: Path, force_overwrite: bool) -> None:
    """Atomically move a completed build into place, preserving old artifacts."""
    backup_dir = None

    _check_replaceable_target(target_dir, force_overwrite)
    if target_dir.exists():
        if _target_is_empty(target_dir):
            target_dir.rmdir()
        else:
            backup_dir = target_dir.parent / (
                f".{target_dir.name}.provikom-backup-{uuid.uuid4().hex}"
            )
            target_dir.rename(backup_dir)

    try:
        temp_dir.rename(target_dir)
    except Exception:
        if backup_dir is not None and backup_dir.exists() and not target_dir.exists():
            backup_dir.rename(target_dir)
        raise

    if backup_dir is not None:
        # The new artifact is already published. Backup cleanup is best-effort;
        # never fail a successful build because an old directory is stubborn.
        shutil.rmtree(backup_dir, ignore_errors=True)


@contextmanager
def atomic_output_directory(
    source_jar_path: Union[str, Path],
    output_directory: Union[str, Path],
    force_overwrite: bool = False,
) -> Iterator[Path]:
    """Yield a temporary build directory and publish it atomically on success.

    The previous output directory is left untouched until the new artifact has
    been fully generated. On failure, the temporary directory is removed and any
    existing artifact remains in place.
    """
    raw_output = Path(output_directory).expanduser()
    _source, target_dir = validate_output_directory(source_jar_path, raw_output)

    parent = target_dir.parent
    parent.mkdir(parents=True, exist_ok=True)

    _check_replaceable_target(target_dir, force_overwrite)

    temp_dir = Path(
        tempfile.mkdtemp(prefix=f".{target_dir.name}.provikom-tmp-", dir=str(parent))
    )
    try:
        yield temp_dir
        _reject_symlink_components(raw_output, "output directory")
        _publish(temp_dir, target_dir, force_overwrite)
    except BaseException:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
