"""Regression tests for dangerous --force and output path combinations."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Optional

from provikom_converter.adapters.base import MissingDependencyError
from provikom_converter.build_safety import (
    BuildPathError,
    atomic_output_directory,
    validate_output_directory,
)
from provikom_converter.orchestration.pipeline import ConverterPipeline
from tests.fixtures import create_minimal_class_bytes, create_synthetic_jar


def _write_jar(path: Path, *, class_path: Optional[str] = None) -> Path:
    manifest = ["Manifest-Version: 1.0", "Main-Class: Example"]
    if class_path:
        manifest.append(f"Class-Path: {class_path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        create_synthetic_jar(
            manifest_lines=manifest,
            classes=[("Example.class", create_minimal_class_bytes(major_version=52))],
        )
    )
    return path


class TestOutputPathValidation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="provikom_safety_")
        self.tmp = Path(self._tmp.name)
        self.jar = _write_jar(self.tmp / "source" / "game.jar")

    def tearDown(self):
        self._tmp.cleanup()

    def test_output_cannot_be_source_jar(self):
        with self.assertRaises(BuildPathError):
            validate_output_directory(self.jar, self.jar)

    def test_output_cannot_be_source_parent(self):
        with self.assertRaises(BuildPathError):
            validate_output_directory(self.jar, self.jar.parent)

    def test_output_cannot_be_source_ancestor(self):
        with self.assertRaises(BuildPathError):
            validate_output_directory(self.jar, self.tmp)

    def test_filesystem_root_is_rejected(self):
        with self.assertRaises(BuildPathError):
            validate_output_directory(self.jar, Path("/"))

    def test_parent_directory_traversal_is_rejected(self):
        with self.assertRaises(BuildPathError):
            validate_output_directory(self.jar, self.jar.parent / ".." / "dist")

    def test_symlink_output_is_rejected(self):
        real = self.tmp / "real-output"
        real.mkdir()
        link = self.tmp / "linked-output"
        link.symlink_to(real, target_is_directory=True)
        with self.assertRaises(BuildPathError):
            validate_output_directory(self.jar, link)

    def test_symlink_to_source_parent_is_rejected(self):
        link = self.tmp / "source-link"
        link.symlink_to(self.jar.parent, target_is_directory=True)
        with self.assertRaises(BuildPathError):
            validate_output_directory(self.jar, link)

    def test_broken_symlink_output_is_rejected(self):
        link = self.tmp / "broken-output"
        link.symlink_to(self.tmp / "missing-target", target_is_directory=True)
        with self.assertRaises(BuildPathError):
            validate_output_directory(self.jar, link)

    def test_output_inside_source_directory_is_allowed(self):
        source, output = validate_output_directory(self.jar, self.jar.parent / "dist")
        self.assertEqual(source, self.jar.resolve())
        self.assertEqual(output, (self.jar.parent / "dist").resolve())

    def test_atomic_context_rejects_overlap_before_creating_files(self):
        with self.assertRaises(BuildPathError):
            with atomic_output_directory(self.jar, self.jar.parent, force_overwrite=True):
                pass
        self.assertTrue(self.jar.is_file())


class TestTransactionalBuilds(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="provikom_atomic_")
        self.tmp = Path(self._tmp.name)
        self.jar = _write_jar(self.tmp / "source" / "game.jar")
        self.out = self.tmp / "artifact"

    def tearDown(self):
        self._tmp.cleanup()

    def test_successful_force_replaces_previous_artifact(self):
        pipeline = ConverterPipeline()
        pipeline.build_artifact(self.jar, self.out)
        (self.out / "stale.txt").write_text("old", encoding="utf-8")

        pipeline.build_artifact(self.jar, self.out, force_overwrite=True)

        self.assertTrue((self.out / "index.html").is_file())
        self.assertFalse((self.out / "stale.txt").exists())

    def test_failed_force_build_preserves_previous_artifact(self):
        pipeline = ConverterPipeline()
        pipeline.build_artifact(self.jar, self.out)
        marker = self.out / "previous-artifact-marker.txt"
        marker.write_text("keep me", encoding="utf-8")

        broken_jar = _write_jar(
            self.tmp / "source" / "broken.jar",
            class_path="lib/Missing.jar",
        )
        with self.assertRaises(MissingDependencyError):
            pipeline.build_artifact(broken_jar, self.out, force_overwrite=True)

        self.assertTrue((self.out / "index.html").is_file())
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep me")

    def test_pipeline_rejects_symlinked_output_before_resolution(self):
        real_output = self.tmp / "real-output"
        real_output.mkdir()
        important = real_output / "important.txt"
        important.write_text("do not delete", encoding="utf-8")
        linked_output = self.tmp / "linked-output"
        linked_output.symlink_to(real_output, target_is_directory=True)

        with self.assertRaises(BuildPathError):
            ConverterPipeline().build_artifact(
                self.jar, linked_output, force_overwrite=True
            )

        self.assertEqual(important.read_text(encoding="utf-8"), "do not delete")
        self.assertTrue(linked_output.is_symlink())
        self.assertFalse((real_output / "index.html").exists())

    def test_pipeline_refuses_force_overwrite_of_unrelated_directory(self):
        self.out.mkdir()
        important = self.out / "important.txt"
        important.write_text("do not delete", encoding="utf-8")

        with self.assertRaises(BuildPathError):
            ConverterPipeline().build_artifact(
                self.jar, self.out, force_overwrite=True
            )

        self.assertEqual(important.read_text(encoding="utf-8"), "do not delete")
        self.assertFalse((self.out / "index.html").exists())

    def test_pipeline_rejects_traversal_output(self):
        traversal_output = self.jar.parent / ".." / "artifact"

        with self.assertRaises(BuildPathError):
            ConverterPipeline().build_artifact(self.jar, traversal_output)

        self.assertFalse((self.tmp / "artifact").exists())

    def test_failed_build_does_not_leave_temporary_directories(self):
        pipeline = ConverterPipeline()
        broken_jar = _write_jar(
            self.tmp / "source" / "broken.jar",
            class_path="lib/Missing.jar",
        )
        with self.assertRaises(MissingDependencyError):
            pipeline.build_artifact(broken_jar, self.out)

        leftovers = [
            p for p in self.tmp.rglob(".*provikom-tmp-*")
        ]
        self.assertEqual(leftovers, [])
        self.assertFalse(self.out.exists())

    def test_output_inside_source_directory_builds_safely(self):
        output = self.jar.parent / "dist"
        ConverterPipeline().build_artifact(self.jar, output)
        self.assertTrue((output / "index.html").is_file())
        self.assertTrue(self.jar.is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
