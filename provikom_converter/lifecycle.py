"""Lifecycle states separating static predictions from runtime evidence.

Static analysis answers "is this archive likely to run?" Artifact generation
answers "did we produce a bundle?" Only browser execution can answer "did the
game actually render and respond to input?" These are deliberately separate
states so a successful build is never mislabeled as runtime-verified.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Union

from provikom_converter.build_safety import refresh_ownership_marker

LIFECYCLE_STATES = (
    "analyzed",
    "candidate",
    "built",
    "runtime_verified",
    "failed",
    "unsupported",
)

STATIC_STATES = ("analyzed", "candidate", "unsupported")
EXECUTION_STATES = ("runtime_verified", "failed")


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _validate_state(state: str) -> str:
    if state not in LIFECYCLE_STATES:
        raise ValueError(
            f"Invalid lifecycle state '{state}'. Expected one of: {', '.join(LIFECYCLE_STATES)}"
        )
    return state


def static_analysis_lifecycle() -> Dict[str, Any]:
    """Lifecycle block for an analysis-only compatibility report."""
    return {
        "state": "analyzed",
        "prediction_only": True,
        "execution_verified": False,
        "source": "static_analysis",
        "verification": {
            "state": "not_run",
            "automated": False,
            "manual": False,
        },
    }


def built_artifact_lifecycle() -> Dict[str, Any]:
    """Lifecycle block for a generated artifact that has not run in a browser."""
    return {
        "state": "built",
        "prediction_only": True,
        "execution_verified": False,
        "source": "artifact_generation",
        "verification": {
            "state": "not_run",
            "automated": False,
            "manual": False,
        },
    }


def make_verification_record(
    *,
    game: str,
    artifact: str,
    state: str,
    checks: Iterable[Dict[str, Any]],
    screenshots: Iterable[str] = (),
    console_errors: Iterable[str] = (),
    runtime_diagnostics: Iterable[str] = (),
    notes: Iterable[str] = (),
    automated: bool = True,
    manual: bool = False,
    duration_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    """Create a self-contained runtime verification evidence record."""
    _validate_state(state)
    if state not in EXECUTION_STATES:
        raise ValueError("A verification record state must be runtime_verified or failed.")

    record: Dict[str, Any] = {
        "schema_version": "1.0",
        "generated_at": _utc_now(),
        "game": game,
        "artifact": artifact,
        "state": state,
        "prediction_only": False,
        "execution_verified": state == "runtime_verified",
        "automated": automated,
        "manual": manual,
        "checks": list(checks),
        "screenshots": list(screenshots),
        "console_errors": list(console_errors),
        "runtime_diagnostics": list(runtime_diagnostics),
        "notes": list(notes),
    }
    if duration_seconds is not None:
        record["duration_seconds"] = round(duration_seconds, 3)
    return record


def write_verification_record(artifact_dir: Union[str, Path], record: Dict[str, Any]) -> Path:
    """Write verification evidence next to the artifact as verification.json."""
    directory = Path(artifact_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "verification.json"
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return path


def apply_verification_to_manifest(
    artifact_dir: Union[str, Path], record: Dict[str, Any]
) -> Dict[str, Any]:
    """Persist verification evidence and update manifest lifecycle state.

    The static ``compatibility`` block is intentionally left unchanged: it is a
    prediction and must not be rewritten to imply execution evidence.
    """
    directory = Path(artifact_dir)
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    state = _validate_state(record["state"])
    if state not in EXECUTION_STATES:
        raise ValueError("Verification records must be runtime_verified or failed.")

    lifecycle = manifest.setdefault("lifecycle", built_artifact_lifecycle())
    lifecycle["state"] = state
    lifecycle["prediction_only"] = False
    lifecycle["execution_verified"] = state == "runtime_verified"
    lifecycle["source"] = "browser_verification"
    lifecycle["verification"] = {
        "state": state,
        "automated": bool(record.get("automated", True)),
        "manual": bool(record.get("manual", False)),
        "record": "verification.json",
        "screenshots": record.get("screenshots", []),
        "console_errors": record.get("console_errors", []),
    }

    generated = manifest.setdefault("generated_files", [])
    if "verification.json" not in generated:
        generated.append("verification.json")

    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    refresh_ownership_marker(directory)
    write_verification_record(directory, record)
    return manifest
