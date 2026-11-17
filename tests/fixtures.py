"""Test fixtures and synthetic archive generators for unit testing."""

from __future__ import annotations

import io
import struct
import zipfile
from typing import List, Optional, Tuple


def create_minimal_class_bytes(
    major_version: int = 52,
    minor_version: int = 0,
    this_class_name: str = "TestClass",
    super_class_name: str = "java/lang/Object",
    referenced_classes: Optional[List[str]] = None,
    methods: Optional[List[str]] = None,
    is_native: bool = False,
) -> bytes:
    """Generate minimal valid JVM classfile bytes conforming to JVMS."""
    if referenced_classes is None:
        referenced_classes = []
    if methods is None:
        methods = ["<init>"]

    # Build constant pool
    # Index 0 is unused in JVM
    cp_entries: List[bytes] = []

    def add_utf8(s: str) -> int:
        b = s.encode("utf-8")
        cp_entries.append(b"\x01" + struct.pack(">H", len(b)) + b)
        return len(cp_entries)

    def add_class(name_idx: int) -> int:
        cp_entries.append(b"\x07" + struct.pack(">H", name_idx))
        return len(cp_entries)

    def add_name_and_type(n_idx: int, d_idx: int) -> int:
        cp_entries.append(b"\x0c" + struct.pack(">HH", n_idx, d_idx))
        return len(cp_entries)

    def add_method_ref(c_idx: int, nat_idx: int) -> int:
        cp_entries.append(b"\x0a" + struct.pack(">HH", c_idx, nat_idx))
        return len(cp_entries)

    # 1. This class
    this_utf = add_utf8(this_class_name)
    this_cls = add_class(this_utf)

    # 2. Super class
    super_utf = add_utf8(super_class_name)
    super_cls = add_class(super_utf)

    # 3. Extra referenced classes
    for ref in referenced_classes:
        r_utf = add_utf8(ref)
        add_class(r_utf)

    # 4. Method references
    for m in methods:
        m_utf = add_utf8(m)
        d_utf = add_utf8("()V")
        nat = add_name_and_type(m_utf, d_utf)
        add_method_ref(super_cls, nat)

    # Header
    out = io.BytesIO()
    out.write(b"\xca\xfe\xba\xbe")  # Magic
    out.write(struct.pack(">HH", minor_version, major_version))
    out.write(struct.pack(">H", len(cp_entries) + 1))  # CP count

    for entry in cp_entries:
        out.write(entry)

    # Access flags (public)
    out.write(struct.pack(">H", 0x0021))
    out.write(struct.pack(">HH", this_cls, super_cls))

    # Interfaces count
    out.write(struct.pack(">H", 0))

    # Fields count
    out.write(struct.pack(">H", 0))

    # Methods count
    out.write(struct.pack(">H", len(methods)))
    for idx, m in enumerate(methods):
        m_flags = 0x0101 if is_native else 0x0001  # ACC_PUBLIC | ACC_NATIVE
        name_idx = 5 + len(referenced_classes) * 2 + idx * 3
        out.write(struct.pack(">HHH", m_flags, 1, 1))  # dummy indices
        out.write(struct.pack(">H", 0))  # attributes count

    # Class attributes count
    out.write(struct.pack(">H", 0))

    return out.getvalue()


def create_synthetic_jar(
    manifest_lines: Optional[List[str]] = None,
    classes: Optional[List[Tuple[str, bytes]]] = None,
    resources: Optional[List[Tuple[str, bytes]]] = None,
) -> bytes:
    """Create an in-memory synthetic JAR file."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if manifest_lines is not None:
            manifest_content = "\r\n".join(manifest_lines) + "\r\n"
            zf.writestr("META-INF/MANIFEST.MF", manifest_content.encode("utf-8"))

        if classes:
            for path, data in classes:
                zf.writestr(path, data)

        if resources:
            for path, data in resources:
                zf.writestr(path, data)

    return buf.getvalue()
