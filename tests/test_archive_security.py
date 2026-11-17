"""Unit tests for archive security and Zip-Slip prevention."""

import io
import unittest
import zipfile

from provikom_converter.analyzer.archive import (
    ArchiveSecurityError,
    SafeArchiveReader,
    parse_manifest,
    sanitize_entry_name,
)
from tests.fixtures import create_synthetic_jar


class TestArchiveSecurity(unittest.TestCase):
    def test_sanitize_entry_name_normal(self):
        self.assertEqual(sanitize_entry_name("com/example/MyClass.class"), "com/example/MyClass.class")
        self.assertEqual(sanitize_entry_name("images\\icon.png"), "images/icon.png")

    def test_sanitize_entry_name_zip_slip_relative(self):
        with self.assertRaises(ArchiveSecurityError):
            sanitize_entry_name("../etc/passwd")

        with self.assertRaises(ArchiveSecurityError):
            sanitize_entry_name("com/../../secret.txt")

        with self.assertRaises(ArchiveSecurityError):
            sanitize_entry_name("foo/bar/..")

    def test_sanitize_entry_name_zip_slip_absolute(self):
        with self.assertRaises(ArchiveSecurityError):
            sanitize_entry_name("/etc/shadow")

        with self.assertRaises(ArchiveSecurityError):
            sanitize_entry_name("C:\\Windows\\System32\\cmd.exe")

    def test_corrupted_archive_rejection(self):
        corrupt_bytes = b"NOT_A_VALID_ZIP_ARCHIVE_DATA"
        reader = SafeArchiveReader(corrupt_bytes)
        with self.assertRaises(ArchiveSecurityError):
            reader.inspect()

    def test_manifest_parsing_unfolding(self):
        # RFC 822 line continuation (leading space)
        manifest_text = (
            "Manifest-Version: 1.0\r\n"
            "Main-Class: com.example.\r\n"
            " VeryLongClassName\r\n"
            "Class-Path: lib/dep1.jar\r\n"
            "  lib/dep2.jar\r\n"
        ).encode("utf-8")

        info = parse_manifest(manifest_text)
        self.assertEqual(info.main_class, "com.example.VeryLongClassName")
        self.assertIn("lib/dep1.jar", info.class_path)
        self.assertIn("lib/dep2.jar", info.class_path)

    def test_safe_archive_reader_normal(self):
        jar_bytes = create_synthetic_jar(
            manifest_lines=["Manifest-Version: 1.0", "Main-Class: test.Main"],
            resources=[("assets/config.txt", b"hello world")],
        )
        reader = SafeArchiveReader(jar_bytes)
        zf, inventory = reader.inspect()
        try:
            self.assertEqual(len(inventory.resources), 1)
            self.assertEqual(inventory.resources[0].path, "assets/config.txt")
            self.assertIsNotNone(inventory.manifest)
            self.assertEqual(inventory.manifest.main_class, "test.Main")
            self.assertEqual(len(inventory.security_warnings), 0)
        finally:
            zf.close()


if __name__ == "__main__":
    unittest.main()
