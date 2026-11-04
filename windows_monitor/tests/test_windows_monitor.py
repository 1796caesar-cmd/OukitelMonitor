"""Offline smoke tests; no Wonderfree account or internet required."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloud import Device, WonderfreeClient
from security import load_credentials, save_credentials
from app import tray_image, history_connect, history_add, history_read


class OfflineTests(unittest.TestCase):
    def test_login_uses_android_compatible_endpoints(self):
        api = WonderfreeClient()
        calls = []
        def fake_request(method, path, **kwargs):
            calls.append((method, path, kwargs))
            return {"code": 200, "data": {"accessToken": {"token": "example-token"}}}
        api._request = fake_request
        api.login("test@example.test", "private-password", "EU")
        self.assertEqual(api.token, "example-token")
        self.assertEqual(api.base, "https://iot-api.quecteleu.com")
        self.assertIn("emailPwdLogin", calls[0][1])
        self.assertEqual(calls[0][2]["data"]["email"], "test@example.test")
        self.assertTrue(calls[0][2]["data"]["pwd"].endswith("\n"))
        self.assertEqual(len(calls[0][2]["data"]["random"]), 16)

    def test_telemetry_parses_id_1_and_powers(self):
        api = WonderfreeClient()
        api.base = "https://example.invalid"
        api.token = "example-token"
        api.wake_reporting = lambda device: None
        api._request = lambda *args, **kwargs: {
            "data": {"customizeTslInfo": [
                {"abId": 1, "resourceValce": "88"},
                {"abId": 4, "resourceValce": "100"},
                {"abId": 5, "resourceValce": "60"},
                {"abId": 14, "resourceValce": "27"},
                {"abId": 2, "resourceValce": "432"}]}}
        t = api.poll(Device("pk", "dk", "P1000E Plus"))
        self.assertEqual((t.battery, t.input_w, t.output_w, t.temperature_c, t.remaining_minutes),
                         (88, 100.0, 60.0, 27.0, 432))

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI only")
    def test_encrypted_credentials_roundtrip(self):
        with tempfile.TemporaryDirectory() as path:
            data = {"email": "test@example.invalid", "password": "test-secret", "region": "EU"}
            save_credentials(Path(path), data)
            self.assertNotIn(b"test-secret", (Path(path) / "credentials.dat").read_bytes())
            self.assertEqual(load_credentials(Path(path)), data)

    def test_percent_icon(self):
        self.assertEqual(tray_image(88).size, (64, 64))
        self.assertEqual(tray_image(100).size, (64, 64))
        self.assertEqual(tray_image(None, stale=True).size, (64, 64))


if __name__ == "__main__":
    unittest.main()
