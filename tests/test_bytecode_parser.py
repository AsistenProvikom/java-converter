"""Unit tests for JVM bytecode parser."""

import unittest

from provikom_converter.analyzer.bytecode import (
    BytecodeParseError,
    ClassFileReader,
    java_version_from_major,
)
from tests.fixtures import create_minimal_class_bytes


class TestBytecodeParser(unittest.TestCase):
    def test_version_mapping(self):
        self.assertEqual(java_version_from_major(52), "Java 8")
        self.assertEqual(java_version_from_major(55), "Java 11 (LTS)")
        self.assertEqual(java_version_from_major(61), "Java 17 (LTS)")
        self.assertEqual(java_version_from_major(65), "Java 21 (LTS)")
        self.assertEqual(java_version_from_major(66), "Java 22")

    def test_parse_valid_class_java8(self):
        data = create_minimal_class_bytes(
            major_version=52,
            this_class_name="com/example/Game",
            referenced_classes=["javax/swing/JFrame", "java/awt/Graphics"],
        )
        parser = ClassFileReader(data, filename="Game.class")
        parsed = parser.parse()

        self.assertEqual(parsed.major_version, 52)
        self.assertEqual(parsed.class_name, "com/example/Game")
        self.assertEqual(parsed.super_class, "java/lang/Object")
        self.assertIn("javax/swing/JFrame", parsed.referenced_classes)
        self.assertIn("java/awt/Graphics", parsed.referenced_classes)
        self.assertIn("javax/swing", parsed.referenced_packages)
        self.assertIn("java/awt", parsed.referenced_packages)

    def test_parse_valid_class_java22(self):
        data = create_minimal_class_bytes(
            major_version=66,
            this_class_name="com/example/ModernGame",
            referenced_classes=["java/lang/Thread"],
        )
        parser = ClassFileReader(data, filename="ModernGame.class")
        parsed = parser.parse()

        self.assertEqual(parsed.major_version, 66)
        self.assertEqual(parsed.class_name, "com/example/ModernGame")

    def test_invalid_magic_number(self):
        invalid_bytes = b"\x00\x00\x00\x00" + b"\x00" * 30
        parser = ClassFileReader(invalid_bytes, filename="bad.class")
        with self.assertRaises(BytecodeParseError):
            parser.parse()

    def test_unexpected_eof(self):
        truncated_bytes = b"\xca\xfe\xba\xbe\x00\x00"
        parser = ClassFileReader(truncated_bytes, filename="truncated.class")
        with self.assertRaises(BytecodeParseError):
            parser.parse()


if __name__ == "__main__":
    unittest.main()
