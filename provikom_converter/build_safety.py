"""Safe, transactional output handling for generated web artifacts.

Artifact builds may use ``--force`` to replace an existing output directory.
Deleting a user-supplied path is inherently dangerous, so every output path is
validated against the input archive before anything is removed. Builds are
written to a temporary sibling directory and published atomically; a failed
build never destroys the previous artifact.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, Tuple, Union


class BuildPathError(ValueError):
    """Raised when an output path could destroy source data or is unsafe."""


def _resolve(path: Union[str, Path]) -> Path:
    return Path(path).expanduser().resolve(strict=False)


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
    source JAR. Filesystem roots and existing output symlinks are rejected.
    """
    source = _resolve(source_jar_path)
    if not source.is_file():
        raise BuildPathError(f"Input archive does not exist or is not a file: {source}")

    raw_output = Path(output_directory).expanduser()
    _reject_path_traversal(raw_output)
    # Validate the caller's raw path before resolving it. Resolving first would
    # hide a symlinked output directory and bypass this rejection.
    _reject_existing_symlink(raw_output, "output directory")
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


def _read_artifact_manifest(directory: Path) -> Dict:
    manifest_path = directory / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        return {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _is_provikom_artifact(directory: Path) -> bool:
    """Return True only for a directory that carries a Provikom build manifest.

    ``--force`` must never wipe an arbitrary non-empty directory. The manifest
    marker is intentionally stricter than checking for index.html or app.js,
    because those names are common in unrelated web projects.
    """
    data = _read_artifact_manifest(directory)
    return (
        isinstance(data.get("provikom_converter_version"), str)
        and data.get("backend") in {"cheerpj", "teavm", "swingjs"}
        and data.get("entry_point") == "index.html"
    )


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
            "contain a Provikom artifact manifest. Move or remove unrelated data "
            "explicitly before using --force."
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
    _source, target_dir = validate_output_directory(source_jar_path, output_directory)

    parent = target_dir.parent
    parent.mkdir(parents=True, exist_ok=True)

    _check_replaceable_target(target_dir, force_overwrite)

    temp_dir = Path(
        tempfile.mkdtemp(prefix=f".{target_dir.name}.provikom-tmp-", dir=str(parent))
    )
    try:
        yield temp_dir
        _publish(temp_dir, target_dir, force_overwrite)
    except BaseException:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
