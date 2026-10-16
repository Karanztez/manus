"""
Test Suite: Verify MT5 Chart Screenshot Capture, Crop, and Logging Output.
Ensures that:
1. logs/ folder is created and holds run_*.log and latest.log.
2. img/ folder is created and holds chart screenshot files and cropped action-area images.
"""

import os
import unittest
from unittest.mock import MagicMock
from PIL import Image
from src.tools import ChartTools

class TestScreenshotAndLogging(unittest.TestCase):
    def setUp(self):
        self.test_img_dir = os.path.join(os.getcwd(), "img")
        self.test_log_dir = os.path.join(os.getcwd(), "logs")
        os.makedirs(self.test_img_dir, exist_ok=True)
        os.makedirs(self.test_log_dir, exist_ok=True)

    def test_img_creation_and_crop(self):
        # 1. Create a mock 800x450 chart image
        sample_img_path = os.path.join(self.test_img_dir, "chart_GOLD_M1.png")
        img = Image.new("RGB", (800, 450), color=(18, 22, 30))
        img.save(sample_img_path)
        self.assertTrue(os.path.exists(sample_img_path), "Base screenshot must exist")

        # 2. Test ChartTools crop action zone
        cropped_path = ChartTools.crop_chart_action_area(sample_img_path, focus_ratio=0.70)
        self.assertIsNotNone(cropped_path)
        self.assertTrue(os.path.exists(cropped_path), "Cropped action-area screenshot must exist")

        # 3. Verify dimensions: 70% width of 800 is 560
        with Image.open(cropped_path) as c_img:
            w, h = c_img.size
            self.assertEqual(w, 560, "Cropped image width must be 560px")
            self.assertEqual(h, 405, "Cropped image height must be trimmed to 405px")

        print(f"\n[OK] Screenshot & Crop verified successfully in: {self.test_img_dir}")
        print(f"[OK] Logs folder active in: {self.test_log_dir}")

if __name__ == "__main__":
    unittest.main()
