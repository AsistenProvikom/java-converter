"""Static inspection of supported Java 8 Swing source projects."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


class SourceProjectError(ValueError):
    """Raised when a source project is outside the documented supported subset."""


@dataclass(frozen=True)
class SourceProject:
    root: Path
    source_root: Path
    main_class: str
    package_name: str
    class_name: str
    java_files: Tuple[Path, ...]
    source_sha256: str
    declared_classes: Tuple[str, ...]
    has_audio: bool
    warnings: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def source_file_count(self) -> int:
        return len(self.java_files)

    def file_records(self) -> List[Dict[str, str]]:
        return [
            {
                "path": path.relative_to(self.root).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in self.java_files
        ]


PACKAGE_RE = re.compile(r"(?m)^\s*package\s+([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*;")
CLASS_RE = re.compile(
    r"\b(?:public\s+)?(?:final\s+|abstract\s+|sealed\s+|non-sealed\s+)*"
    r"(?:class|interface|enum|record)\s+([A-Za-z_$][\w$]*)"
)
MAIN_RE = re.compile(
    r"\bpublic\s+static\s+void\s+main\s*\(\s*String\s*"
    r"(?:\.\.\.\s*\w+|\[\s*\]\s*\w+|\w+\s*\[\s*\])\s*\)"
)
IMPORT_RE = re.compile(
    r"(?m)^\s*import\s+(?:static\s+)?([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)"
)
UNSUPPORTED_IMPORTS = {
    "javafx.": "JavaFX is not supported by the SwingJS source backend.",
    "org.eclipse.swt.": "SWT is not supported by the SwingJS source backend.",
}
RISKY_IMPORTS = {
    "javax.sound.": "Audio APIs are not verified under SwingJS; browser audio requires manual testing.",
    "java.applet.AudioClip": "Applet audio APIs are not verified under SwingJS.",
    "java.net.": "Network APIs may require a same-origin proxy and are not verified.",
    "java.io.": "Filesystem APIs run against SwingJS's in-memory filesystem; persistence is not verified.",
    "java.nio.file.": "Filesystem APIs run against SwingJS's in-memory filesystem; persistence is not verified.",
    "java.lang.reflect.": "Reflection is not verified under SwingJS.",
    "java.lang.Thread": "Threading compatibility is not verified under SwingJS.",
    "java.awt.event.KeyListener": "Direct KeyListener input may require Swing key bindings under SwingJS.",
    "java.awt.Robot": "java.awt.Robot is not supported in the browser.",
}


def _without_comments_and_strings(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    text = re.sub(r"//[^\n]*", " ", text)
    text = re.sub(r'"(?:\\.|[^"\\])*"', '""', text)
    text = re.sub(r"'(?:\\.|[^'\\])*'", "''", text)
    return text


def _safe_source_files(root: Path, source_root: Path) -> Tuple[Path, ...]:
    files: List[Path] = []
    for path in sorted(source_root.rglob("*.java")):
        for parent in (path, *path.parents):
            if parent == root.parent:
                break
            if parent.is_symlink():
                raise SourceProjectError(
                    "Refusing symlinked Java source path: {}".format(parent)
                )
        try:
            path.resolve().relative_to(root)
        except ValueError as exc:
            raise SourceProjectError(
                "Java source escapes the project directory: {}".format(path)
            ) from exc
        files.append(path)
    return tuple(files)


def _project_hash(root: Path, files: Sequence[Path]) -> str:
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def inspect_source_project(
    directory: Path,
    *,
    main_class: Optional[str] = None,
) -> SourceProject:
    """Validate a Java 8 Swing source project and locate its entry point.

    The supported layout is ``<project>/src/**/*.java``. Source files are read
    for structure and imports only; they are not executed on the host during
    inspection.
    """
    raw_root = Path(directory).expanduser()
    if raw_root.is_symlink():
        raise SourceProjectError("Refusing symlinked source project: {}".format(raw_root))
    root = raw_root.resolve()
    if not root.is_dir():
        raise SourceProjectError("Source project directory not found: {}".format(root))
    source_root = root / "src"
    if not source_root.is_dir():
        raise SourceProjectError(
            "Source project must contain a src/ directory: {}".format(root)
        )
    files = _safe_source_files(root, source_root)
    if not files:
        raise SourceProjectError("Source project has no .java files under src/: {}".format(root))

    declared: Dict[str, str] = {}
    main_classes: List[str] = []
    warnings: List[str] = []
    has_audio = False
    for path in files:
        if path.name == "module-info.java":
            raise SourceProjectError(
                "Java module descriptors are not supported by the Java 8 SwingJS subset."
            )
        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise SourceProjectError(
                "Java source is not UTF-8: {}".format(path)
            ) from exc
        text = _without_comments_and_strings(raw)
        package_match = PACKAGE_RE.search(text)
        package = package_match.group(1) if package_match else ""
        classes = CLASS_RE.findall(text)
        for simple in classes:
            declared[(package + "." + simple) if package else simple] = path.as_posix()
        for match in MAIN_RE.finditer(text):
            before = text[: match.start()]
            class_matches = list(CLASS_RE.finditer(before))
            if not class_matches:
                raise SourceProjectError(
                    "Could not associate main() with a class in {}".format(path)
                )
            simple = class_matches[-1].group(1)
            main_classes.append((package + "." + simple) if package else simple)

        imported = IMPORT_RE.findall(text)
        for prefix, message in UNSUPPORTED_IMPORTS.items():
            if any(name.startswith(prefix) for name in imported):
                raise SourceProjectError("{} ({})".format(message, path.name))
        for prefix, message in RISKY_IMPORTS.items():
            if any(name.startswith(prefix) for name in imported):
                if message not in warnings:
                    warnings.append(message)
                if prefix.startswith(("javax.sound.", "java.applet.AudioClip")):
                    has_audio = True

    if not declared:
        raise SourceProjectError("No Java classes were found under {}".format(source_root))

    unique_mains = sorted(set(main_classes))
    if main_class:
        selected = main_class
        if selected not in declared:
            raise SourceProjectError(
                "Requested main class '{}' is not declared in the project. Available classes: {}".format(
                    selected, ", ".join(sorted(declared))
                )
            )
        if selected not in unique_mains:
            raise SourceProjectError(
                "Requested main class '{}' does not declare public static void main(String[]).".format(
                    selected
                )
            )
    elif len(unique_mains) == 1:
        selected = unique_mains[0]
    elif not unique_mains:
        raise SourceProjectError(
            "No public static void main(String[]) entry point was found. "
            "SwingJS artifacts require an explicit Java entry point."
        )
    else:
        raise SourceProjectError(
            "Multiple main classes found: {}. Select one with --main-class.".format(
                ", ".join(unique_mains)
            )
        )

    package_name, _, class_name = selected.rpartition(".")
    if not class_name:
        class_name = selected
        package_name = ""
    return SourceProject(
        root=root,
        source_root=source_root,
        main_class=selected,
        package_name=package_name,
        class_name=class_name,
        java_files=files,
        source_sha256=_project_hash(root, files),
        declared_classes=tuple(sorted(declared)),
        has_audio=has_audio,
        warnings=tuple(warnings),
    )
