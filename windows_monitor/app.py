"""Oukitel Monitor for Windows — always-visible battery percentage in system tray.

Windows 10/11, including 32-bit Windows, when packaged for that architecture.
No external server except the existing Wonderfree / Quectel cloud API.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import sqlite3
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

import pystray
from PIL import Image, ImageDraw, ImageFont

from cloud import AuthError, Device, Telemetry, WonderfreeClient, WonderfreeError
from security import delete_credentials, load_credentials, save_credentials

try:
    import winreg
except ImportError:
    winreg = None

APP_NAME = "Oukitel Monitor"
APP_VERSION = "1.0 Windows"
AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_NAME = "OukitelMonitorWindows"
DATA_DIR = Path(os.getenv("LOCALAPPDATA") or str(Path.home())) / "OukitelMonitorWindows"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = DATA_DIR / "settings.json"
DB_FILE = DATA_DIR / "history.sqlite"

BG = "#0B1516"
CARD = "#162B28"
CARD2 = "#203A34"
GREEN = "#29CB65"
GREEN_DARK = "#125A36"
WHITE = "#F2F8F4"
MUTED = "#94B5A5"
AMBER = "#F4B43E"
RED = "#FF7272"


def auto_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    return f'"{sys.executable}" "{Path(__file__).resolve()}" --minimized'


def is_autostart() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY) as k:
            return bool(winreg.QueryValueEx(k, AUTOSTART_NAME)[0])
    except OSError:
        return False


def set_autostart(enabled: bool) -> None:
    if winreg is None:
        return
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, AUTOSTART_NAME, 0, winreg.REG_SZ, auto_command())
        else:
            try:
                winreg.DeleteValue(k, AUTOSTART_NAME)
            except FileNotFoundError:
                pass


def read_settings() -> dict:
    try:
        obj = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data: dict) -> None:
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, SETTINGS_FILE)


def history_connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_FILE, timeout=5)
    con.execute("CREATE TABLE IF NOT EXISTS samples (ts INTEGER PRIMARY KEY, battery INTEGER, input_w REAL, output_w REAL)")
    return con


def history_add(con: sqlite3.Connection, battery: int | None, input_w: float | None, output_w: float | None) -> None:
    con.execute("INSERT OR REPLACE INTO samples (ts, battery, input_w, output_w) VALUES (?, ?, ?, ?)",
                (int(time.time()), battery, input_w, output_w))
    con.execute("DELETE FROM samples WHERE ts < ?", (int(time.time()) - 31 * 86400,))
    con.commit()


def history_read(hours: int) -> list[tuple[int, int]]:
    with history_connect() as con:
        rows = con.execute("SELECT ts,battery FROM samples WHERE ts >= ? AND battery IS NOT NULL ORDER BY ts",
                           (int(time.time()) - hours * 3600,)).fetchall()
    if len(rows) > 1500:
        # Subsample existing measurements only; no made-up values.
        step = max(1, len(rows) // 1400)
        samples = rows[::step]
        if samples[-1] != rows[-1]:
            samples.append(rows[-1])
        return samples
    return rows


def tray_image(level: int | None, stale: bool = False) -> Image.Image:
    """The large source is scaled to a small system-tray icon by Windows."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    shade = "#697E77" if stale or level is None else ("#E85B5B" if level <= 15 else "#DFAB30" if level <= 30 else "#17A957")
    draw.rounded_rectangle((2, 6, 61, 57), radius=12, fill=shade, outline="#D4FFE8", width=2)
    label = "--" if level is None else str(level)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 35 if len(label) <= 2 else 27)
    except OSError:
        font = ImageFont.load_default()
    bounds = draw.textbbox((0, 0), label, font=font)
    w, h = bounds[2] - bounds[0], bounds[3] - bounds[1]
    draw.text(((size - w) / 2 - bounds[0], (size - h) / 2 - bounds[1] - 1), label,
              fill="#FFFFFF", font=font)
    return img


class MonitorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.settings = read_settings()
        self.commands: queue.Queue[tuple] = queue.Queue()
        self.events: queue.Queue[tuple] = queue.Queue()
        self.stop = threading.Event()
        self.credentials = load_credentials(DATA_DIR)
        self.level: int | None = None
        self.last_success: float = 0
        self.telemetry: Telemetry | None = None
        self.device_name = "P1000E Plus"
        self.devices: list[Device] = []
        self.connected = False
        self.current_interval = int(self.settings.get("interval", 60))
        if self.current_interval not in (30, 60, 180, 300, 600):
            self.current_interval = 60
        self.root.title("Oukitel Monitor — Windows")
        self.root.geometry("520x680")
        self.root.minsize(450, 570)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        self.tray = pystray.Icon("oukitel-monitor", tray_image(None), "Oukitel Monitor — очікування даних",
                                menu=pystray.Menu(
                                    pystray.MenuItem("Відкрити", lambda *_: self.events.put(("show",)), default=True),
                                    pystray.MenuItem("Оновити заряд", lambda *_: self.commands.put(("poll",))),
                                    pystray.Menu.SEPARATOR,
                                    pystray.MenuItem("Вийти з програми", lambda *_: self.events.put(("exit",))),
                                ))
        self._build_ui()
        self.tray.run_detached()
        self.worker = threading.Thread(target=self._worker, name="WonderfreeWorker", daemon=True)
        self.worker.start()
        if self.credentials:
            self.commands.put(("login", dict(self.credentials), False))
        else:
            self._login_mode()
        self.root.after(250, self._drain)
        self.root.after(30000, self._freshness)

    def _frame(self, parent: tk.Widget, bg: str = CARD) -> tk.Frame:
        return tk.Frame(parent, bg=bg, highlightthickness=0)

    def _text(self, parent: tk.Widget, text: str, size=13, color=WHITE,
              bold=False, bg=CARD, **kwargs) -> tk.Label:
        return tk.Label(parent, text=text, font=("Segoe UI", size, "bold" if bold else "normal"),
                        fg=color, bg=bg, **kwargs)

    def _button(self, parent: tk.Widget, text: str, command, color=GREEN_DARK) -> tk.Button:
        return tk.Button(parent, text=text, command=command, font=("Segoe UI", 10, "bold"),
                         bg=color, fg=WHITE, activebackground=GREEN, activeforeground=WHITE,
                         relief="flat", padx=14, pady=9, cursor="hand2")

    def _build_ui(self) -> None:
        outer = self._frame(self.root, BG)
        outer.pack(fill="both", expand=True, padx=21, pady=17)
        header = self._frame(outer, BG)
        header.pack(fill="x")
        self._text(header, "OUKITEL MONITOR", 20, GREEN, True, BG).pack(side="left")
        self._text(header, "WINDOWS", 10, MUTED, True, BG).pack(side="right")
        self.connection_label = self._text(outer, "●  Очікування підключення", 11, AMBER, bg=BG)
        self.connection_label.pack(anchor="w", pady=(4, 10))

        self.main_area = self._frame(outer, BG)
        self.main_area.pack(fill="both", expand=True)
        self.dashboard = self._frame(self.main_area, BG)
        self.login_panel = self._frame(self.main_area, CARD)
        self._build_dashboard()
        self._build_login()
        self.dashboard.pack(fill="both", expand=True)

    def _build_dashboard(self) -> None:
        battery_box = self._frame(self.dashboard)
        battery_box.pack(fill="x", pady=(0, 12))
        self._text(battery_box, "ЗАРЯД АКУМУЛЯТОРА", 11, MUTED, True).pack(pady=(17, 0))
        self.battery_canvas = tk.Canvas(battery_box, width=310, height=207, bg=CARD,
                                        highlightthickness=0)
        self.battery_canvas.pack(fill="x", pady=0)
        self._draw_battery()
        self.name_label = self._text(battery_box, self.device_name, 12, WHITE)
        self.name_label.pack(pady=(0, 15))

        metric_row = self._frame(self.dashboard, BG)
        metric_row.pack(fill="x")
        self.metric_input = self._metric(metric_row, "INPUT", "— Вт", "↓")
        self.metric_output = self._metric(metric_row, "OUTPUT", "— Вт", "↑")
        metric_row2 = self._frame(self.dashboard, BG)
        metric_row2.pack(fill="x", pady=(7, 0))
        self.metric_temp = self._metric(metric_row2, "ТЕМПЕРАТУРА", "— °C", "°")
        self.metric_time = self._metric(metric_row2, "ЧАС РОБОТИ", "—", "◷")

        history_box = self._frame(self.dashboard)
        history_box.pack(fill="both", expand=True, pady=(13, 0))
        history_top = self._frame(history_box)
        history_top.pack(fill="x", padx=15, pady=(10, 0))
        self._text(history_top, "Графік заряду", 13, WHITE, True).pack(side="left")
        self.period = tk.StringVar(value="24 години")
        period = ttk.Combobox(history_top, textvariable=self.period, values=("24 години", "7 днів", "30 днів"),
                              state="readonly", width=12, font=("Segoe UI", 9))
        period.pack(side="right")
        period.bind("<<ComboboxSelected>>", lambda _: self._draw_graph())
        self.graph = tk.Canvas(history_box, height=128, bg=CARD, highlightthickness=0)
        self.graph.pack(fill="both", expand=True, padx=8, pady=(3, 10))
        self.graph.bind("<Configure>", lambda _: self._draw_graph())

        self.last_updated = self._text(self.dashboard, "Останні дані: —", 10, MUTED, bg=BG)
        self.last_updated.pack(anchor="w", pady=(9, 3))
        controls = self._frame(self.dashboard, BG)
        controls.pack(fill="x", pady=(2, 0))
        self._button(controls, "Оновити зараз", lambda: self.commands.put(("poll",))).pack(side="left")
        self._button(controls, "Налаштування", self._settings_window, CARD2).pack(side="right")

    def _metric(self, parent: tk.Widget, title: str, default: str, symbol: str) -> tk.Label:
        box = self._frame(parent)
        box.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._text(box, f"{symbol}  {title}", 10, MUTED, True).pack(pady=(11, 4))
        value = self._text(box, default, 17, WHITE, True)
        value.pack(pady=(0, 12))
        return value

    def _build_login(self) -> None:
        self._text(self.login_panel, "Вхід у Wonderfree", 20, GREEN, True).pack(pady=(22, 9))
        self._text(self.login_panel, "Використай обліковий запис зі смартфона.", 11, MUTED,
                   wraplength=400).pack(pady=(0, 19))
        fields = self._frame(self.login_panel)
        fields.pack(fill="x", padx=22)
        self._text(fields, "Email", 11, MUTED).pack(anchor="w")
        self.email_entry = tk.Entry(fields, font=("Segoe UI", 12), bg=BG, fg=WHITE,
                                    insertbackground=WHITE, relief="flat")
        self.email_entry.pack(fill="x", ipady=9, pady=(3, 15))
        self._text(fields, "Пароль", 11, MUTED).pack(anchor="w")
        self.pass_entry = tk.Entry(fields, show="●", font=("Segoe UI", 12), bg=BG, fg=WHITE,
                                   insertbackground=WHITE, relief="flat")
        self.pass_entry.pack(fill="x", ipady=9, pady=(3, 15))
        self._text(fields, "Регіон", 11, MUTED).pack(anchor="w")
        self.region_var = tk.StringVar(value="EU")
        ttk.Combobox(fields, textvariable=self.region_var, values=("EU", "US", "CN"),
                     state="readonly", width=16).pack(anchor="w", pady=(3, 18))
        self.login_btn = self._button(fields, "Увійти", self._login_from_form)
        self.login_btn.pack(fill="x", pady=(5, 13))
        self.login_note = self._text(self.login_panel, "Пароль шифрується у Windows (DPAPI).", 10,
                                     MUTED, wraplength=390)
        self.login_note.pack(pady=(4, 23))

    def _login_mode(self) -> None:
        self.dashboard.pack_forget()
        self.login_panel.pack(fill="x", pady=(22, 0))

    def _dashboard_mode(self) -> None:
        self.login_panel.pack_forget()
        self.dashboard.pack(fill="both", expand=True)

    def _login_from_form(self) -> None:
        email, password, region = self.email_entry.get().strip(), self.pass_entry.get(), self.region_var.get()
        if not email or not password:
            self.login_note.configure(text="Введи email і пароль", fg=RED)
            return
        self.login_btn.configure(state="disabled")
        self.login_note.configure(text="Підключення до Wonderfree…", fg=AMBER)
        self.commands.put(("login", {"email": email, "password": password, "region": region}, True))

    def _draw_battery(self) -> None:
        c = self.battery_canvas
        c.delete("all")
        w, h = max(c.winfo_width(), 310), max(c.winfo_height(), 207)
        x, y, side = w / 2, h / 2, 76
        c.create_oval(x - side, y - side, x + side, y + side,
                      outline=GREEN_DARK, width=17)
        if self.level is not None:
            color = RED if self.level <= 15 else AMBER if self.level <= 30 else GREEN
            # Tk's positive extent is counter-clockwise; start at 12 o'clock.
            c.create_arc(x - side, y - side, x + side, y + side,
                         start=90, extent=-3.6 * self.level, outline=color,
                         style=tk.ARC, width=17)
        c.create_text(x, y - 5, text=f"{self.level}%" if self.level is not None else "—%",
                      fill=WHITE, font=("Segoe UI", 39, "bold"))
        c.create_text(x, y + 34, text="LiFePO4", fill=MUTED, font=("Segoe UI", 10))

    def _draw_graph(self) -> None:
        if not self.graph.winfo_exists():
            return
        c = self.graph
        c.delete("all")
        w = max(c.winfo_width(), 220)
        h = max(c.winfo_height(), 120)
        left, top, right, bottom = 37, 13, w - 10, h - 22
        for p in (0, 25, 50, 75, 100):
            yy = bottom - (bottom - top) * (p / 100)
            c.create_line(left, yy, right, yy, fill=CARD2)
            c.create_text(27, yy, text=str(p), fill=MUTED, font=("Segoe UI", 8))
        hours = {"24 години": 24, "7 днів": 168, "30 днів": 720}[self.period.get()]
        try:
            rows = history_read(hours)
        except sqlite3.Error:
            rows = []
        if not rows:
            c.create_text((left + right) / 2, (top + bottom) / 2,
                          text="Історія з'явиться після опитування", fill=MUTED,
                          font=("Segoe UI", 10))
            return
        end_t = time.time()
        start_t = end_t - hours * 3600
        coords = []
        for ts, battery in rows:
            xx = left + (right - left) * max(0, min(1, (ts - start_t) / (hours * 3600)))
            yy = bottom - (bottom - top) * (battery / 100)
            coords.extend((xx, yy))
        if len(coords) >= 4:
            c.create_line(*coords, fill=GREEN, width=2, smooth=False)
        if len(coords) >= 2:
            x, y = coords[-2:]
            c.create_oval(x - 3, y - 3, x + 3, y + 3, fill=GREEN, outline=WHITE)
        c.create_text(left, h - 8, text=f"−{hours} год", anchor="w", fill=MUTED, font=("Segoe UI", 8))
        c.create_text(right, h - 8, text="Зараз", anchor="e", fill=MUTED, font=("Segoe UI", 8))

    def _settings_window(self) -> None:
        if hasattr(self, "settings_window") and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return
        w = tk.Toplevel(self.root)
        self.settings_window = w
        w.title("Налаштування — Oukitel Monitor")
        w.geometry("410x360")
        w.configure(bg=BG)
        inner = self._frame(w, BG)
        inner.pack(fill="both", expand=True, padx=22, pady=20)
        self._text(inner, "Налаштування", 19, GREEN, True, BG).pack(anchor="w", pady=(0, 16))
        self._text(inner, "Інтервал оновлення", 11, MUTED, bg=BG).pack(anchor="w")
        opts = {"30 секунд": 30, "1 хвилина": 60, "3 хвилини": 180,
                "5 хвилин": 300, "10 хвилин": 600}
        label = next((x for x, v in opts.items() if v == self.current_interval), "1 хвилина")
        self.refresh_choice = tk.StringVar(value=label)
        c = ttk.Combobox(inner, values=tuple(opts), textvariable=self.refresh_choice, state="readonly")
        c.pack(fill="x", pady=(5, 14))

        autostart = tk.BooleanVar(value=is_autostart())
        tk.Checkbutton(inner, text="Запускати разом із Windows", variable=autostart,
                       font=("Segoe UI", 11), fg=WHITE, bg=BG,
                       selectcolor=CARD2, activebackground=BG, activeforeground=WHITE).pack(anchor="w")
        alert_on = tk.BooleanVar(value=bool(self.settings.get("alerts", True)))
        tk.Checkbutton(inner, text="Повідомлення при 5% і 100%", variable=alert_on,
                       font=("Segoe UI", 11), fg=WHITE, bg=BG,
                       selectcolor=CARD2, activebackground=BG, activeforeground=WHITE).pack(anchor="w", pady=(5, 12))

        if len(self.devices) > 1:
            self._text(inner, "Станція", 11, MUTED, bg=BG).pack(anchor="w")
            names = [d.name for d in self.devices]
            choice = ttk.Combobox(inner, values=names, state="readonly")
            choice.set(self.device_name if self.device_name in names else names[0])
            choice.pack(fill="x", pady=(4, 10))
        else:
            choice = None

        def save() -> None:
            try:
                set_autostart(autostart.get())
            except OSError as ex:
                messagebox.showerror("Помилка", f"Не вдалося встановити автозапуск: {ex}", parent=w)
                return
            self.current_interval = opts[self.refresh_choice.get()]
            self.settings["interval"] = self.current_interval
            self.settings["alerts"] = alert_on.get()
            save_settings(self.settings)
            if choice is not None:
                index = choice.current()
                if index >= 0 and self.devices[index].dk != next((d.dk for d in self.devices if d.name == self.device_name), None):
                    self.commands.put(("choose", self.devices[index].dk))
            self.commands.put(("poll",))
            w.destroy()

        self._button(inner, "Зберегти", save).pack(fill="x", pady=(5, 10))
        self._button(inner, "Змінити обліковий запис", lambda: (w.destroy(), self._login_mode()), CARD2).pack(fill="x")

    def _worker(self) -> None:
        client = WonderfreeClient()
        con = history_connect()
        credentials = dict(self.credentials) if self.credentials else None
        selected_device: Device | None = None
        devices: list[Device] = []
        next_poll = 0.0
        last_battery: int | None = None
        while not self.stop.is_set():
            timeout = max(0.1, min(5, next_poll - time.monotonic())) if credentials else 5
            try:
                cmd = self.commands.get(timeout=timeout)
            except queue.Empty:
                cmd = ("poll",) if credentials and time.monotonic() >= next_poll else ("noop",)
            if cmd[0] == "exit":
                break
            try:
                if cmd[0] == "login":
                    candidate, save_if_success = cmd[1], cmd[2]
                    client.login(candidate["email"], candidate["password"], candidate["region"])
                    devices = client.devices()
                    preferred = candidate.get("preferred_device_key")
                    selected_device = next((d for d in devices if d.dk == preferred), None)
                    if selected_device is None:
                        selected_device = next((d for d in devices if "p1000" in d.name.lower()), devices[0])
                    candidate["preferred_device_key"] = selected_device.dk
                    # Save only after successful login, encrypted for this Windows account.
                    if save_if_success or credentials != candidate:
                        save_credentials(DATA_DIR, candidate)
                    credentials = candidate
                    last_battery = None
                    self.events.put(("connected", selected_device.name, devices))
                    next_poll = time.monotonic()
                elif cmd[0] == "choose" and devices and credentials:
                    new_device = next((d for d in devices if d.dk == cmd[1]), None)
                    if new_device:
                        selected_device = new_device
                        credentials["preferred_device_key"] = selected_device.dk
                        save_credentials(DATA_DIR, credentials)
                        client.last_wake = 0.0
                        last_battery = None
                        self.events.put(("device", selected_device.name))
                        next_poll = time.monotonic()
                elif cmd[0] == "poll" and credentials:
                    if selected_device is None or time.monotonic() - client.login_mono > 90 * 60:
                        client.login(credentials["email"], credentials["password"], credentials["region"])
                        devices = client.devices()
                        selected_device = next((d for d in devices if d.dk == credentials.get("preferred_device_key")), devices[0])
                    try:
                        value = client.poll(selected_device)
                    except AuthError:
                        client.login(credentials["email"], credentials["password"], credentials["region"])
                        value = client.poll(selected_device)
                    if value.battery is None:
                        raise WonderfreeError("Wonderfree не повернув рівень заряду")
                    history_add(con, value.battery, value.input_w, value.output_w)
                    self.events.put(("telemetry", value, selected_device.name))
                    if last_battery is not None and self.settings.get("alerts", True):
                        if last_battery > 5 >= value.battery:
                            self.events.put(("notify", "Заряд станції впав до 5% або нижче", value.battery))
                        elif last_battery < 100 == value.battery:
                            self.events.put(("notify", "Станція повністю заряджена", value.battery))
                    last_battery = value.battery
                    next_poll = time.monotonic() + self.current_interval
            except (WonderfreeError, OSError, KeyError) as exc:
                self.events.put(("error", str(exc)))
                if cmd[0] == "login" and cmd[2]:
                    self.events.put(("login_failed", str(exc)))
                next_poll = time.monotonic() + max(30, self.current_interval)
            except Exception as exc:
                # Don't include potentially sensitive payloads in error UI/logs.
                self.events.put(("error", f"Не вдалося обробити дані ({type(exc).__name__})"))
                if cmd[0] == "login" and cmd[2]:
                    self.events.put(("login_failed", "Помилка підключення"))
                next_poll = time.monotonic() + max(30, self.current_interval)
        con.close()

    def _drain(self) -> None:
        while True:
            try:
                evt = self.events.get_nowait()
            except queue.Empty:
                break
            kind = evt[0]
            if kind == "show":
                self.show()
            elif kind == "exit":
                self.quit()
                return
            elif kind == "connected":
                self.connected = True
                self.device_name, self.devices = evt[1], evt[2]
                self.name_label.configure(text=self.device_name)
                self._dashboard_mode()
                self.pass_entry.delete(0, tk.END)
                self.connection_label.configure(text="●  Підключено, отримую дані…", fg=AMBER)
                self.login_btn.configure(state="normal")
            elif kind == "device":
                self.device_name = evt[1]
                self.name_label.configure(text=self.device_name)
                self.level = None
                self._draw_battery()
            elif kind == "telemetry":
                self._set_telemetry(evt[1], evt[2])
            elif kind == "notify":
                try:
                    if self.tray.HAS_NOTIFICATION:
                        self.tray.notify(evt[1], APP_NAME)
                except Exception:
                    pass
            elif kind == "error":
                self.connection_label.configure(text="●  " + evt[1][:65], fg=RED)
                self._refresh_tray(stale=True)
            elif kind == "login_failed":
                self.login_btn.configure(state="normal")
                self.login_note.configure(text=evt[1][:110], fg=RED)
        self.root.after(350, self._drain)

    def _set_telemetry(self, t: Telemetry, device_name: str) -> None:
        self.level = t.battery
        self.telemetry = t
        self.device_name = device_name
        self.last_success = time.time()
        self.name_label.configure(text=device_name)
        self._draw_battery()
        self.metric_input.configure(text=f"{t.input_w:.0f} Вт" if t.input_w is not None else "— Вт")
        self.metric_output.configure(text=f"{t.output_w:.0f} Вт" if t.output_w is not None else "— Вт")
        self.metric_temp.configure(text=f"{t.temperature_c:.0f} °C" if t.temperature_c is not None else "— °C")
        if t.remaining_minutes is not None and t.remaining_minutes >= 0 and t.output_w is not None and t.input_w is not None and t.output_w > t.input_w:
            self.metric_time.configure(text=f"{t.remaining_minutes // 60} год {t.remaining_minutes % 60} хв")
        else:
            self.metric_time.configure(text="—")
        self.connection_label.configure(text="●  Дані отримано", fg=GREEN)
        self.last_updated.configure(text="Останнє опитування: " + datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
        self._refresh_tray(stale=False)
        self._draw_graph()

    def _refresh_tray(self, stale: bool) -> None:
        try:
            self.tray.icon = tray_image(self.level, stale=stale)
            label = f"{self.level}%" if self.level is not None else "—"
            self.tray.title = (f"Oukitel: {label}"
                               + (" (немає актуальних даних)" if stale else ""))
        except Exception:
            pass

    def _freshness(self) -> None:
        if self.last_success and time.time() - self.last_success > max(180, self.current_interval * 3):
            self.connection_label.configure(text="●  Дані застаріли", fg=AMBER)
            self._refresh_tray(stale=True)
        self.root.after(30000, self._freshness)

    def show(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide(self) -> None:
        self.root.withdraw()

    def quit(self) -> None:
        self.stop.set()
        self.commands.put(("exit",))
        try:
            self.tray.stop()
        except Exception:
            pass
        self.root.destroy()


def already_running() -> bool:
    if os.name != "nt":
        return False
    import ctypes
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\OukitelMonitorWindowsSingleInstance")
    if not handle:
        return False
    # Keep mutex open for the whole process (Windows releases it on process exit).
    return ctypes.windll.kernel32.GetLastError() == 183


def main() -> None:
    if already_running():
        return
    root = tk.Tk()
    MonitorApp(root)
    if "--minimized" in sys.argv:
        root.withdraw()
    root.mainloop()


if __name__ == "__main__":
    main()
