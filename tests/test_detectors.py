"""Unit tests for feature detectors and compatibility heuristics."""

import unittest

from provikom_converter.analyzer.bytecode import ClassFileReader
from provikom_converter.analyzer.rules import FeatureDetector
from tests.fixtures import create_minimal_class_bytes


class TestFeatureDetectors(unittest.TestCase):
    def test_detect_swing_and_awt(self):
        data = create_minimal_class_bytes(
            referenced_classes=[
                "javax/swing/JFrame",
                "javax/swing/JButton",
                "java/awt/Graphics",
                "java/awt/event/ActionListener",
            ]
        )
        parsed = ClassFileReader(data).parse()
        detector = FeatureDetector([parsed], manifest_classpath=[])
        features = detector.detect()

        gui_names = [f.name for f in features.gui_frameworks]
        self.assertIn("Java Swing", gui_names)
        self.assertIn("Java AWT", gui_names)

    def test_detect_audio_apis(self):
        data = create_minimal_class_bytes(
            referenced_classes=[
                "javax/sound/sampled/AudioSystem",
                "javax/sound/sampled/Clip",
            ]
        )
        parsed = ClassFileReader(data).parse()
        detector = FeatureDetector([parsed], manifest_classpath=[])
        features = detector.detect()

        audio_names = [f.name for f in features.audio_apis]
        self.assertTrue(any("javax.sound.sampled" in name for name in audio_names))

    def test_detect_netbeans_absolute_layout(self):
        data = create_minimal_class_bytes(
            referenced_classes=["org/netbeans/lib/awtextra/AbsoluteLayout"]
        )
        parsed = ClassFileReader(data).parse()
        detector = FeatureDetector([parsed], manifest_classpath=["lib/AbsoluteLayout.jar"])
        features = detector.detect()

        lib_names = [f.name for f in features.external_libraries]
        self.assertIn("NetBeans AbsoluteLayout", lib_names)

    def test_detect_native_code(self):
        data = create_minimal_class_bytes(
            is_native=True,
            methods=["nativeMethod"],
        )
        parsed = ClassFileReader(data).parse()
        self.assertTrue(parsed.has_native_methods)

        detector = FeatureDetector([parsed], manifest_classpath=[])
        features = detector.detect()

        native_names = [f.name for f in features.native_features]
        self.assertTrue(any("Native" in n for n in native_names))


if __name__ == "__main__":
    unittest.main()
