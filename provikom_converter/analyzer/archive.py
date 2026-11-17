"""Archive inspection module for Provikom Converter.

Handles safe inspection of untrusted JAR and ZIP archives:
- Zip-slip prevention
- Zip-bomb and resource exhaustion guards
- Manifest and classpath discovery
- Resource and native library inventory
- Embedded archive detection
"""

from __future__ import annotations

import io
import os
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import Dict, List, Optional, Set, Tuple


class ArchiveSecurityError(Exception):
    """Raised when an archive violates security constraints."""
    pass


@dataclass
class ManifestInfo:
    main_class: Optional[str] = None
    class_path: List[str] = field(default_factory=list)
    created_by: Optional[str] = None
    build_jdk: Optional[str] = None
    raw_attributes: Dict[str, str] = field(default_factory=dict)


@dataclass
class ArchiveEntry:
    path: str
    file_size: int
    compressed_size: int
    entry_type: str  # 'class', 'resource', 'native', 'nested_jar', 'manifest', 'other'
    extension: str


@dataclass
class ArchiveInventory:
    total_entries: int
    total_uncompressed_bytes: int
    total_compressed_bytes: int
    classes: List[str] = field(default_factory=list)
    resources: List[ArchiveEntry] = field(default_factory=list)
    native_libraries: List[ArchiveEntry] = field(default_factory=list)
    nested_archives: List[ArchiveEntry] = field(default_factory=list)
    manifest: Optional[ManifestInfo] = None
    security_warnings: List[str] = field(default_factory=list)
    resource_extensions: Dict[str, int] = field(default_factory=dict)


# Security thresholds
MAX_TOTAL_UNCOMPRESSED_SIZE = 500 * 1024 * 1024  # 500 MB
MAX_ENTRY_COUNT = 50_000
MAX_COMPRESSION_RATIO = 100.0  # 100:1 ratio alert

NATIVE_EXTENSIONS = {".dll", ".so", ".dylib", ".jnilib"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".mid", ".midi", ".aiff", ".au"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico"}
FONT_EXTENSIONS = {".ttf", ".otf", ".woff", ".woff2"}


def sanitize_entry_name(name: str) -> str:
    """Check for Zip-Slip path traversal vectors."""
    if not name:
        raise ArchiveSecurityError("Empty archive entry name detected")
    
    # Normalize path separators
    normalized = name.replace("\\", "/")
    
    # Detect absolute path or directory traversal
    if normalized.startswith("/") or normalized.startswith("../") or "/../" in normalized or normalized.endswith("/.."):
        raise ArchiveSecurityError(f"Potential zip-slip vulnerability in entry: '{name}'")
    
    # Check for Windows drive letters (e.g., C:)
    if len(normalized) > 1 and normalized[1] == ":":
        raise ArchiveSecurityError(f"Windows drive path traversal in entry: '{name}'")

    return normalized


def parse_manifest(content: bytes) -> ManifestInfo:
    """Parse a JAR MANIFEST.MF according to the standard specification.
    
    Handles RFC 822 line continuation (lines starting with a single space).
    """
    text = content.decode("utf-8", errors="replace")
    lines: List[str] = []
    
    # Unfold wrapped lines
    for line in text.splitlines():
        if line.startswith(" ") and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)

    attrs: Dict[str, str] = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, val = line.split(":", 1)
            attrs[key.strip()] = val.strip()

    main_class = attrs.get("Main-Class")
    class_path_str = attrs.get("Class-Path", "")
    # Class-Path in manifest is space-delimited
    class_path = [cp.strip() for cp in class_path_str.split() if cp.strip()]
    created_by = attrs.get("Created-By")
    build_jdk = attrs.get("Build-Jdk") or attrs.get("Build-Jdk-Spec")

    return ManifestInfo(
        main_class=main_class,
        class_path=class_path,
        created_by=created_by,
        build_jdk=build_jdk,
        raw_attributes=attrs,
    )


class SafeArchiveReader:
    """Safely opens and inspects JAR archives without extracting them to disk."""

    def __init__(self, file_path_or_bytes: str | bytes, name: Optional[str] = None):
        if isinstance(file_path_or_bytes, bytes):
            self.source = io.BytesIO(file_path_or_bytes)
            self.display_name = name or "<bytes>"
        else:
            self.source = file_path_or_bytes
            self.display_name = name or os.path.basename(file_path_or_bytes)

    def inspect(self) -> Tuple[zipfile.ZipFile, ArchiveInventory]:
        try:
            zf = zipfile.ZipFile(self.source, "r")
        except zipfile.BadZipFile as e:
            raise ArchiveSecurityError(f"Corrupt or invalid ZIP/JAR archive: {e}") from e

        infolist = zf.infolist()
        total_entries = len(infolist)
        if total_entries > MAX_ENTRY_COUNT:
            zf.close()
            raise ArchiveSecurityError(
                f"Archive exceeds maximum allowed entry count ({total_entries} > {MAX_ENTRY_COUNT})"
            )

        total_uncompressed = 0
        total_compressed = 0
        classes: List[str] = []
        resources: List[ArchiveEntry] = []
        native_libs: List[ArchiveEntry] = []
        nested_archives: List[ArchiveEntry] = []
        warnings: List[str] = []
        res_exts: Dict[str, int] = {}
        manifest: Optional[ManifestInfo] = None

        for info in infolist:
            # Zip-Slip check
            clean_name = sanitize_entry_name(info.filename)
            if clean_name.endswith("/"):
                # directory entry
                continue

            # Zip bomb ratio / total size check
            total_uncompressed += info.file_size
            total_compressed += info.compress_size

            if total_uncompressed > MAX_TOTAL_UNCOMPRESSED_SIZE:
                zf.close()
                raise ArchiveSecurityError(
                    f"Archive uncompressed size exceeds safe limit ({total_uncompressed} > {MAX_TOTAL_UNCOMPRESSED_SIZE} bytes)"
                )

            if info.compress_size > 0:
                ratio = info.file_size / info.compress_size
                if ratio > MAX_COMPRESSION_RATIO and info.file_size > 1024 * 1024:
                    warnings.append(
                        f"Entry '{clean_name}' has suspicious compression ratio ({ratio:.1f}:1)"
                    )

            # Classify entry
            ext = os.path.splitext(clean_name)[1].lower()
            res_exts[ext] = res_exts.get(ext, 0) + 1

            if clean_name.upper() == "META-INF/MANIFEST.MF":
                entry_type = "manifest"
                try:
                    manifest_data = zf.read(info)
                    manifest = parse_manifest(manifest_data)
                except Exception as e:
                    warnings.append(f"Failed to parse manifest: {e}")
            elif clean_name.endswith(".class"):
                entry_type = "class"
                classes.append(clean_name)
            elif ext in NATIVE_EXTENSIONS:
                entry_type = "native"
                entry = ArchiveEntry(
                    path=clean_name,
                    file_size=info.file_size,
                    compressed_size=info.compress_size,
                    entry_type=entry_type,
                    extension=ext,
                )
                native_libs.append(entry)
            elif ext in {".jar", ".zip", ".war"}:
                entry_type = "nested_jar"
                entry = ArchiveEntry(
                    path=clean_name,
                    file_size=info.file_size,
                    compressed_size=info.compress_size,
                    entry_type=entry_type,
                    extension=ext,
                )
                nested_archives.append(entry)
                warnings.append(
                    f"Embedded archive detected: '{clean_name}' ({info.file_size} bytes)"
                )
            else:
                entry_type = "resource"
                entry = ArchiveEntry(
                    path=clean_name,
                    file_size=info.file_size,
                    compressed_size=info.compress_size,
                    entry_type=entry_type,
                    extension=ext,
                )
                resources.append(entry)

        inventory = ArchiveInventory(
            total_entries=total_entries,
            total_uncompressed_bytes=total_uncompressed,
            total_compressed_bytes=total_compressed,
            classes=classes,
            resources=resources,
            native_libraries=native_libs,
            nested_archives=nested_archives,
            manifest=manifest,
            security_warnings=warnings,
            resource_extensions=res_exts,
        )

        return zf, inventory
