"""Wonderfree / Quectel read-only telemetry client for Oukitel Monitor Windows.

Uses the same documented login + polling endpoints and device identifiers as the
OukitelMonitor Android project. API is unofficial: verify with your hardware.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad


REGIONS = {
    "EU": ("https://iot-api.quecteleu.com", "3aRNUwWahjyANa7WfBK2wCCkxCexB6nXxKJwXxfePvzf", "E.SP.4294967410"),
    "US": ("https://iot-api.quectelus.com", "pUTp5goB1bLinprRQMmK3EPiiuPiGrJtKUNptWRXVmP", "U.SP.8589934603"),
    "CN": ("https://iot-gateway.quectel.com", "EufftRJSuWuVY7c6txzGifV9bJcfXHAFa7hXY5doXSn7", "C.DM.5903.1"),
}


class WonderfreeError(Exception):
    pass


class AuthError(WonderfreeError):
    pass


@dataclass
class Device:
    pk: str
    dk: str
    name: str


@dataclass
class Telemetry:
    battery: int | None
    input_w: float | None
    output_w: float | None
    temperature_c: float | None
    remaining_minutes: int | None


class WonderfreeClient:
    def __init__(self) -> None:
        self.http = requests.Session()
        self.base = ""
        self.token = ""
        self.login_mono = 0.0
        self.last_wake = 0.0

    def _request(self, method: str, path: str, *, data: dict | None = None,
                 json_data: dict | None = None, authenticated: bool = True) -> dict[str, Any]:
        headers = {
            "X-Q-Language": "en",
            "quec-random-url": str(uuid.uuid4()),
            "app-info": "[Pixel][Google][raven][33]",
        }
        if authenticated:
            headers["Authorization"] = self.token
        try:
            resp = self.http.request(method, self.base + path, headers=headers,
                                     data=data, json=json_data, timeout=(10, 20))
            if resp.status_code in (401, 403):
                raise AuthError("Wonderfree вимагає повторної авторизації")
            resp.raise_for_status()
            payload = resp.json()
        except AuthError:
            raise
        except (requests.RequestException, ValueError) as exc:
            raise WonderfreeError("Немає відповіді від Wonderfree") from exc
        if not isinstance(payload, dict):
            raise WonderfreeError("Невідомий формат відповіді Wonderfree")
        code = payload.get("code", 200)
        msg = str(payload.get("msg") or "")
        if code in (401, 403) or any(s in msg.lower() for s in
                                     ("token validation failed", "token expired", "invalid token", "unauthorized")):
            raise AuthError("Токен Wonderfree закінчився")
        if code not in (0, 200, "0", "200", None):
            raise WonderfreeError(msg or "Помилка Wonderfree")
        return payload

    def login(self, email: str, password: str, region: str) -> None:
        self.base, api_secret, domain = REGIONS[region]
        rnd = "".join(secrets.choice("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz") for _ in range(16))
        md5 = hashlib.md5(rnd.encode("ascii")).hexdigest().upper()
        aes_key = md5[8:24]
        aes_iv = aes_key[8:16] + aes_key[:8]
        cipher = AES.new(aes_key.encode("ascii"), AES.MODE_CBC, iv=aes_iv.encode("ascii"))
        # Android Base64.DEFAULT includes line wrapping and a final newline.
        encrypted_password = base64.encodebytes(cipher.encrypt(pad(password.encode("utf-8"), 16))).decode("ascii")
        signature = hashlib.sha256((email + encrypted_password + rnd + api_secret).encode("utf-8")).hexdigest()
        reply = self._request("POST", "/v2/enduser/enduserapi/emailPwdLogin",
                              data={"pwd": encrypted_password, "email": email, "random": rnd,
                                    "userDomain": domain, "signature": signature}, authenticated=False)
        token = ((reply.get("data") or {}).get("accessToken") or {}).get("token")
        if not isinstance(token, str) or not token:
            raise AuthError("Вхід не підтверджено. Перевір email, пароль і регіон.")
        self.token = token
        self.login_mono = time.monotonic()
        self.last_wake = 0.0

    def devices(self) -> list[Device]:
        reply = self._request("GET", "/v2/binding/enduserapi/userDeviceList?pageNumber=1&pageSize=50")
        records = ((reply.get("data") or {}).get("list") or [])
        devices: list[Device] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            pk, dk = str(record.get("productKey") or ""), str(record.get("deviceKey") or "")
            if pk and dk:
                name = str(record.get("deviceName") or record.get("productName") or "Oukitel")
                devices.append(Device(pk, dk, name))
        if not devices:
            raise WonderfreeError("У Wonderfree не знайдено станцій")
        return devices

    def wake_reporting(self, device: Device) -> None:
        """Same high-frequency TELEMETRY request as Android, never toggles outputs."""
        if time.monotonic() - self.last_wake < 300:
            return
        try:
            self._request("POST", "/v2/binding/enduserapi/batchControlDevice",
                          json_data={"data": '[{"high_frequency_reporting":3}]',
                                     "deviceList": [{"deviceKey": device.dk, "productKey": device.pk}],
                                     "cacheTime": 60, "isCache": 1, "isCover": 1,
                                     "dataFormat": 0, "type": 2})
            self.last_wake = time.monotonic()
        except WonderfreeError:
            # Normal polling remains possible when reporting request is rejected.
            pass

    def poll(self, device: Device) -> Telemetry:
        self.wake_reporting(device)
        query = urlencode({"pk": device.pk, "dk": device.dk})
        reply = self._request("GET", "/v2/binding/enduserapi/getDeviceBusinessAttributes?" + query)
        items = (reply.get("data") or {}).get("customizeTslInfo") or []
        values: dict[int, float] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                abid = int(item.get("abId", -1))
                val = float(item.get("resourceValce"))
                if abid in (1, 2, 3, 4, 5, 14) and val == val:
                    values[abid] = val
            except (ValueError, TypeError, OverflowError):
                pass
        if not values:
            raise WonderfreeError("Станція не передала показники")
        battery = round(values[1]) if 1 in values else None
        battery = max(0, min(100, battery)) if battery is not None else None
        remaining = round(values[2]) if 2 in values else None
        return Telemetry(battery=battery, input_w=values.get(4), output_w=values.get(5),
                         temperature_c=values.get(14), remaining_minutes=remaining)
