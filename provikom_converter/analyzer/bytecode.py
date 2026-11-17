"""JVM Bytecode and Classfile parser for Provikom Converter.

Safely parses compiled Java class files without executing any bytecode.
Extracts class metadata, constant pool symbols, inheritance hierarchy,
method references, and opcode patterns.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


class BytecodeParseError(Exception):
    """Raised when a class file is malformed or invalid."""
    pass


JAVA_VERSION_MAP: Dict[int, str] = {
    45: "Java 1.1",
    46: "Java 1.2",
    47: "Java 1.3",
    48: "Java 1.4",
    49: "Java 5",
    50: "Java 6",
    51: "Java 7",
    52: "Java 8",
    53: "Java 9",
    54: "Java 10",
    55: "Java 11 (LTS)",
    56: "Java 12",
    57: "Java 13",
    58: "Java 14",
    59: "Java 15",
    60: "Java 16",
    61: "Java 17 (LTS)",
    62: "Java 18",
    63: "Java 19",
    64: "Java 20",
    65: "Java 21 (LTS)",
    66: "Java 22",
    67: "Java 23",
    68: "Java 24",
    69: "Java 25",
}


def java_version_from_major(major: int) -> str:
    """Return a human-readable Java version string."""
    return JAVA_VERSION_MAP.get(major, f"Java {major - 44} (major {major})")


@dataclass
class MethodRef:
    class_name: str
    method_name: str
    descriptor: str


@dataclass
class FieldRef:
    class_name: str
    field_name: str
    descriptor: str


@dataclass
class ParsedClassFile:
    class_name: str
    super_class: Optional[str]
    interfaces: List[str]
    major_version: int
    minor_version: int
    access_flags: int
    referenced_classes: Set[str] = field(default_factory=set)
    referenced_packages: Set[str] = field(default_factory=set)
    method_refs: List[MethodRef] = field(default_factory=list)
    field_refs: List[FieldRef] = field(default_factory=list)
    string_constants: Set[str] = field(default_factory=set)
    has_native_methods: bool = False
    methods: List[str] = field(default_factory=list)


# Constant Pool Tags
CONSTANT_Utf8 = 1
CONSTANT_Integer = 3
CONSTANT_Float = 4
CONSTANT_Long = 5
CONSTANT_Double = 6
CONSTANT_Class = 7
CONSTANT_String = 8
CONSTANT_Fieldref = 9
CONSTANT_Methodref = 10
CONSTANT_InterfaceMethodref = 11
CONSTANT_NameAndType = 12
CONSTANT_MethodHandle = 15
CONSTANT_MethodType = 16
CONSTANT_Dynamic = 17
CONSTANT_InvokeDynamic = 18
CONSTANT_Module = 19
CONSTANT_Package = 20

ACC_NATIVE = 0x0100


class ClassFileReader:
    """Zero-execution JVM Classfile binary parser."""

    def __init__(self, data: bytes, filename: str = "<unknown>"):
        self.data = data
        self.size = len(data)
        self.offset = 0
        self.filename = filename

    def read_u1(self) -> int:
        if self.offset + 1 > self.size:
            raise BytecodeParseError(f"Unexpected EOF in {self.filename}")
        val = self.data[self.offset]
        self.offset += 1
        return val

    def read_u2(self) -> int:
        if self.offset + 2 > self.size:
            raise BytecodeParseError(f"Unexpected EOF in {self.filename}")
        val = struct.unpack_from(">H", self.data, self.offset)[0]
        self.offset += 2
        return val

    def read_u4(self) -> int:
        if self.offset + 4 > self.size:
            raise BytecodeParseError(f"Unexpected EOF in {self.filename}")
        val = struct.unpack_from(">I", self.data, self.offset)[0]
        self.offset += 4
        return val

    def read_bytes(self, length: int) -> bytes:
        if self.offset + length > self.size:
            raise BytecodeParseError(f"Unexpected EOF in {self.filename}")
        val = self.data[self.offset : self.offset + length]
        self.offset += length
        return val

    def parse(self) -> ParsedClassFile:
        magic = self.read_u4()
        if magic != 0xCAFEBABE:
            raise BytecodeParseError(f"Invalid magic number 0x{magic:08X} in {self.filename}")

        minor_version = self.read_u2()
        major_version = self.read_u2()

        # Parse constant pool
        cp_count = self.read_u2()
        cp: List[Optional[Tuple[int, ...]]] = [None] * cp_count
        i = 1
        while i < cp_count:
            tag = self.read_u1()
            if tag == CONSTANT_Utf8:
                length = self.read_u2()
                raw = self.read_bytes(length)
                val = raw.decode("utf-8", errors="replace")
                cp[i] = (tag, val)
            elif tag in (CONSTANT_Integer, CONSTANT_Float):
                self.offset += 4
                cp[i] = (tag, None)
            elif tag in (CONSTANT_Long, CONSTANT_Double):
                self.offset += 8
                cp[i] = (tag, None)
                i += 1  # 8-byte entries take 2 constant pool slots
            elif tag in (CONSTANT_Class, CONSTANT_String, CONSTANT_MethodType, CONSTANT_Module, CONSTANT_Package):
                idx = self.read_u2()
                cp[i] = (tag, idx)
            elif tag in (CONSTANT_Fieldref, CONSTANT_Methodref, CONSTANT_InterfaceMethodref):
                class_idx = self.read_u2()
                nat_idx = self.read_u2()
                cp[i] = (tag, class_idx, nat_idx)
            elif tag == CONSTANT_NameAndType:
                name_idx = self.read_u2()
                desc_idx = self.read_u2()
                cp[i] = (tag, name_idx, desc_idx)
            elif tag == CONSTANT_MethodHandle:
                self.offset += 3
                cp[i] = (tag, None)
            elif tag in (CONSTANT_Dynamic, CONSTANT_InvokeDynamic):
                self.offset += 4
                cp[i] = (tag, None)
            else:
                raise BytecodeParseError(f"Unknown constant pool tag {tag} at index {i} in {self.filename}")
            i += 1

        def get_utf8(idx: int) -> str:
            if 0 < idx < len(cp) and cp[idx] and cp[idx][0] == CONSTANT_Utf8:
                return cp[idx][1]
            return ""

        def get_class_name(idx: int) -> str:
            if 0 < idx < len(cp) and cp[idx] and cp[idx][0] == CONSTANT_Class:
                name_idx = cp[idx][1]
                return get_utf8(name_idx)
            return ""

        access_flags = self.read_u2()
        this_class_idx = self.read_u2()
        super_class_idx = self.read_u2()

        this_class_name = get_class_name(this_class_idx) or self.filename
        super_class_name = get_class_name(super_class_idx) if super_class_idx > 0 else None

        # Interfaces
        interfaces_count = self.read_u2()
        interfaces: List[str] = []
        for _ in range(interfaces_count):
            iface_idx = self.read_u2()
            iface_name = get_class_name(iface_idx)
            if iface_name:
                interfaces.append(iface_name)

        # Fields
        fields_count = self.read_u2()
        for _ in range(fields_count):
            _f_access = self.read_u2()
            _f_name_idx = self.read_u2()
            _f_desc_idx = self.read_u2()
            attr_count = self.read_u2()
            for _ in range(attr_count):
                _a_name_idx = self.read_u2()
                a_len = self.read_u4()
                self.offset += a_len

        # Methods
        methods_count = self.read_u2()
        methods: List[str] = []
        has_native = False
        for _ in range(methods_count):
            m_access = self.read_u2()
            if m_access & ACC_NATIVE:
                has_native = True
            m_name_idx = self.read_u2()
            m_desc_idx = self.read_u2()
            m_name = get_utf8(m_name_idx)
            methods.append(m_name)
            attr_count = self.read_u2()
            for _ in range(attr_count):
                _a_name_idx = self.read_u2()
                a_len = self.read_u4()
                self.offset += a_len

        # Collect references from constant pool
        referenced_classes: Set[str] = set()
        referenced_packages: Set[str] = set()
        method_refs: List[MethodRef] = []
        field_refs: List[FieldRef] = []
        strings: Set[str] = set()

        for item in cp:
            if not item:
                continue
            tag = item[0]
            if tag == CONSTANT_Class:
                name = get_utf8(item[1])
                if name:
                    referenced_classes.add(name)
                    if "/" in name:
                        pkg = name.rsplit("/", 1)[0]
                        referenced_packages.add(pkg)
            elif tag in (CONSTANT_Methodref, CONSTANT_InterfaceMethodref):
                cls_name = get_class_name(item[1])
                nat = cp[item[2]] if 0 < item[2] < len(cp) else None
                if nat and nat[0] == CONSTANT_NameAndType:
                    m_name = get_utf8(nat[1])
                    m_desc = get_utf8(nat[2])
                    method_refs.append(MethodRef(cls_name, m_name, m_desc))
            elif tag == CONSTANT_Fieldref:
                cls_name = get_class_name(item[1])
                nat = cp[item[2]] if 0 < item[2] < len(cp) else None
                if nat and nat[0] == CONSTANT_NameAndType:
                    f_name = get_utf8(nat[1])
                    f_desc = get_utf8(nat[2])
                    field_refs.append(FieldRef(cls_name, f_name, f_desc))
            elif tag == CONSTANT_String:
                s_val = get_utf8(item[1])
                if s_val:
                    strings.add(s_val)

        return ParsedClassFile(
            class_name=this_class_name,
            super_class=super_class_name,
            interfaces=interfaces,
            major_version=major_version,
            minor_version=minor_version,
            access_flags=access_flags,
            referenced_classes=referenced_classes,
            referenced_packages=referenced_packages,
            method_refs=method_refs,
            field_refs=field_refs,
            string_constants=strings,
            has_native_methods=has_native,
            methods=methods,
        )
