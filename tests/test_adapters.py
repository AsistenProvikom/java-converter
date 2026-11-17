"""Unit tests for backend adapters and compatibility evaluators."""

import unittest

from provikom_converter.adapters.cheerpj import CheerpJAdapter
from provikom_converter.adapters.swingjs import SwingJSAdapter
from provikom_converter.adapters.teavm import TeaVMAdapter
from provikom_converter.analyzer.archive import ArchiveInventory
from provikom_converter.analyzer.bytecode import ClassFileReader
from provikom_converter.analyzer.compatibility import CompatibilityStatus
from provikom_converter.analyzer.rules import FeatureDetector
from tests.fixtures import create_minimal_class_bytes


class TestAdapters(unittest.TestCase):
    def setUp(self):
        self.cheerpj = CheerpJAdapter()
        self.teavm = TeaVMAdapter()
        self.swingjs = SwingJSAdapter()

        self.inventory = ArchiveInventory(
            total_entries=10,
            total_uncompressed_bytes=5000,
            total_compressed_bytes=2000,
            classes=["Game.class"],
        )

    def test_cheerpj_swing_supported(self):
        data = create_minimal_class_bytes(
            major_version=52,
            referenced_classes=["javax/swing/JFrame", "java/awt/Graphics"],
        )
        parsed = ClassFileReader(data).parse()
        features = FeatureDetector([parsed], []).detect()

        eval_res = self.cheerpj.evaluate_compatibility(self.inventory, features, [52])
        self.assertEqual(eval_res.status, CompatibilityStatus.SUPPORTED)
        self.assertFalse(eval_res.is_open_source)

    def test_teavm_swing_blocked(self):
        data = create_minimal_class_bytes(
            major_version=52,
            referenced_classes=["javax/swing/JFrame"],
        )
        parsed = ClassFileReader(data).parse()
        features = FeatureDetector([parsed], []).detect()

        eval_res = self.teavm.evaluate_compatibility(self.inventory, features, [52])
        self.assertEqual(eval_res.status, CompatibilityStatus.UNSUPPORTED)
        self.assertTrue(eval_res.is_open_source)
        self.assertTrue(any("javax.swing" in b for b in eval_res.blockers))

    def test_swingjs_requires_source(self):
        data = create_minimal_class_bytes(
            major_version=52,
            referenced_classes=["javax/swing/JFrame"],
        )
        parsed = ClassFileReader(data).parse()
        features = FeatureDetector([parsed], []).detect()

        eval_res = self.swingjs.evaluate_compatibility(self.inventory, features, [52])
        self.assertEqual(eval_res.status, CompatibilityStatus.REQUIRES_SOURCE)
        self.assertTrue(eval_res.is_open_source)


if __name__ == "__main__":
    unittest.main()
