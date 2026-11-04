"""Offline regression tests for multiple battery rules and numeric tray icon."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alert_rules import (
    notification_messages,
    load_threshold_rules,
    multi_notification_messages,
)
from tray_style import tray_image


class AlertRulesTests(unittest.TestCase):
    def test_legacy_single_rule_kept(self):
        self.assertEqual(len(notification_messages(28, 20, low_threshold=25)), 1)
        self.assertEqual(notification_messages(20, 18, low_threshold=25), [])
        self.assertEqual(notification_messages(78, 85, high_threshold=80, low_enabled=False),
                         ["Заряд станції досяг 80%"])
        self.assertEqual(notification_messages(99, 100), ["Станція повністю заряджена (100%)"])

    def test_migration_from_windows_11(self):
        old = {"alerts": True, "notify_low": True, "low_threshold": 90,
               "notify_high": False, "high_threshold": 100}
        self.assertEqual(load_threshold_rules(old, "low"),
                         [{"threshold": 90, "enabled": True}])
        self.assertEqual(load_threshold_rules(old, "high"),
                         [{"threshold": 100, "enabled": False}])

    def test_explicit_empty_list_stays_empty(self):
        self.assertEqual(load_threshold_rules({"low_rules": []}, "low"), [])

    def test_invalid_or_duplicate_saved_rules_are_sanitized(self):
        rules = [{"threshold": 90, "enabled": True},
                 {"threshold": 90, "enabled": True},
                 {"threshold": 0, "enabled": True},
                 {"threshold": 70, "enabled": False}]
        self.assertEqual(load_threshold_rules({"low_rules": rules}, "low"),
                         [{"threshold": 90, "enabled": True},
                          {"threshold": 70, "enabled": False}])

    def test_multiple_low_crossed_without_exact_measurements(self):
        low = [{"threshold": x, "enabled": True} for x in (90, 70, 50, 30)]
        messages = multi_notification_messages(92, 48, low, [])
        self.assertEqual(len(messages), 3)
        self.assertIn("нижче 90%", messages[0])
        self.assertIn("нижче 70%", messages[1])
        self.assertIn("нижче 50%", messages[2])
        self.assertEqual(multi_notification_messages(48, 48, low, []), [])
        self.assertEqual(multi_notification_messages(48, 47, low, []), [])

    def test_strict_below_90(self):
        low = [{"threshold": 90, "enabled": True}]
        self.assertEqual(multi_notification_messages(92, 90, low, []), [])
        self.assertEqual(len(multi_notification_messages(92, 88, low, [])), 1)
        self.assertEqual(len(multi_notification_messages(90, 88, low, [])), 1)

    def test_multiple_high_thresholds_and_disabling(self):
        high = [{"threshold": 95, "enabled": True},
                {"threshold": 100, "enabled": True},
                {"threshold": 98, "enabled": False}]
        msgs = multi_notification_messages(92, 100, [], high)
        self.assertEqual(len(msgs), 2)
        self.assertIn("95%", msgs[0])
        self.assertIn("100%", msgs[1])
        self.assertEqual(multi_notification_messages(100, 99, [], high), [])

    def test_no_first_poll_alert_and_invalid(self):
        rules = [{"threshold": 90, "enabled": True}]
        self.assertEqual(multi_notification_messages(None, 80, rules, []), [])
        self.assertEqual(multi_notification_messages(105, 80, rules, []), [])
        self.assertEqual(multi_notification_messages(90, None, rules, []), [])
        self.assertEqual(multi_notification_messages(80, 100, rules, []), [])

    def test_numeric_tray_without_ring_or_fill(self):
        for n in (None, 5, 90, 100):
            im = tray_image(n)
            self.assertEqual(im.size, (64, 64))
            self.assertEqual(im.mode, "RGBA")
            self.assertEqual(im.getpixel((0, 0))[3], 0)
            self.assertEqual(im.getpixel((63, 0))[3], 0)
            self.assertEqual(im.getpixel((0, 63))[3], 0)
            self.assertGreater(max(im.getchannel("A").getdata()), 0)
        self.assertEqual(tray_image(90, stale=True).size, (64, 64))


if __name__ == "__main__":
    unittest.main()
