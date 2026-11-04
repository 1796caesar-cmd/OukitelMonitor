"""Offline regression checks for notification thresholds and outline tray icon."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alert_rules import notification_messages
from tray_style import tray_image


class AlertRuleTests(unittest.TestCase):
    def test_low_level_threshold(self):
        self.assertEqual(len(notification_messages(28, 20, low_threshold=25)), 1)
        self.assertEqual(notification_messages(20, 18, low_threshold=25), [])
        self.assertEqual(notification_messages(28, 27, low_threshold=25), [])

    def test_high_level_threshold(self):
        self.assertEqual(notification_messages(78, 85, high_threshold=80, low_enabled=False),
                         ["Заряд станції досяг 80%"])
        self.assertEqual(notification_messages(85, 88, high_threshold=80), [])

    def test_disable_individual_alerts(self):
        self.assertEqual(notification_messages(10, 4, low_enabled=False), [])
        self.assertEqual(notification_messages(90, 100, high_enabled=False), [])

    def test_full_charge_default(self):
        self.assertEqual(notification_messages(99, 100), ["Станція повністю заряджена (100%)"])
        self.assertEqual(notification_messages(100, 100), [])

    def test_large_jump_and_invalid_readings(self):
        self.assertEqual(len(notification_messages(70, 0, low_threshold=20)), 1)
        self.assertEqual(notification_messages(None, 0), [])
        self.assertEqual(notification_messages(110, 0), [])

    def test_ring_without_fill(self):
        for p in (None, 5, 88, 100):
            img = tray_image(p)
            self.assertEqual(img.mode, "RGBA")
            self.assertEqual(img.size, (64, 64))
            self.assertEqual(img.getpixel((0, 0))[3], 0)
            self.assertEqual(img.getpixel((32, 14))[3], 0)
        self.assertEqual(tray_image(88, stale=True).size, (64, 64))


if __name__ == "__main__":
    unittest.main()
