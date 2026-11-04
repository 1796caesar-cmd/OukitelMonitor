"""Apply Oukitel Monitor Windows notification / tray icon update at build time.

The Android app remains untouched. Run after repository checkout, before the
Windows smoke tests and PyInstaller packaging. The current GitHub repository
has app.py 1.0 as its baseline, so this targeted patch keeps the update small.
"""
from pathlib import Path

APP = Path(__file__).with_name('app.py')


def replace_once(source: str, old: str, new: str, step: str) -> str:
    found = source.count(old)
    if found != 1:
        raise RuntimeError(f'{step}: expected one matching source segment; found {found}')
    return source.replace(old, new, 1)


source = APP.read_text(encoding='utf-8')
if 'APP_VERSION = "1.1 Windows"' in source:
    print('Windows 1.1 code already patched')
    raise SystemExit(0)

source = replace_once(source,
    'APP_VERSION = "1.0 Windows"', 'APP_VERSION = "1.1 Windows"', 'version')

source = replace_once(source,
    'from security import delete_credentials, load_credentials, save_credentials',
    'from security import delete_credentials, load_credentials, save_credentials\nfrom alert_rules import notification_messages',
    'import notification rules')

# The tray icon is the user-requested unfilled white circle with a legible
# percentage numeral. Its 64x64 output preserves the previous offline tests.
start = source.find('def tray_image(level: int | None, stale: bool = False) -> Image.Image:')
end = source.find('\n\nclass MonitorApp:', start)
if start < 0 or end < 0 or source.find('def tray_image(', start + 1) >= 0:
    raise RuntimeError('tray image section not found uniquely')
source = source[:start] + 'from tray_style import tray_image\n' + source[end:]

source = replace_once(source,
    '        w.geometry("410x360")',
    '        w.geometry("450x555")\n        w.minsize(430, 530)',
    'resize settings for two thresholds')

source = replace_once(source, '''        alert_on = tk.BooleanVar(value=bool(self.settings.get("alerts", True)))
        tk.Checkbutton(inner, text="Повідомлення при 5% і 100%", variable=alert_on,
                       font=("Segoe UI", 11), fg=WHITE, bg=BG,
                       selectcolor=CARD2, activebackground=BG, activeforeground=WHITE).pack(anchor="w", pady=(5, 12))''',
'''        legacy_alerts = bool(self.settings.get("alerts", True))
        low_on = tk.BooleanVar(value=bool(self.settings.get("notify_low", legacy_alerts)))
        high_on = tk.BooleanVar(value=bool(self.settings.get("notify_high", legacy_alerts)))
        low_pct = tk.StringVar(value=str(self.settings.get("low_threshold", 5)))
        high_pct = tk.StringVar(value=str(self.settings.get("high_threshold", 100)))

        self._text(inner, "Сповіщення про заряд", 12, GREEN, True, BG).pack(anchor="w", pady=(6, 6))
        low_row = self._frame(inner, BG)
        low_row.pack(fill="x", pady=(2, 8))
        tk.Checkbutton(low_row, text="Знизився до", variable=low_on,
                       font=("Segoe UI", 11), fg=WHITE, bg=BG,
                       selectcolor=CARD2, activebackground=BG, activeforeground=WHITE).pack(side="left")
        tk.Spinbox(low_row, from_=1, to=100, width=4, textvariable=low_pct,
                   font=("Segoe UI", 11), justify="center",
                   bg=CARD2, fg=WHITE, buttonbackground=CARD2,
                   insertbackground=WHITE).pack(side="left", padx=(10, 4))
        self._text(low_row, "%", 11, WHITE, bg=BG).pack(side="left")

        high_row = self._frame(inner, BG)
        high_row.pack(fill="x", pady=(2, 6))
        tk.Checkbutton(high_row, text="Досяг", variable=high_on,
                       font=("Segoe UI", 11), fg=WHITE, bg=BG,
                       selectcolor=CARD2, activebackground=BG, activeforeground=WHITE).pack(side="left")
        tk.Spinbox(high_row, from_=1, to=100, width=4, textvariable=high_pct,
                   font=("Segoe UI", 11), justify="center",
                   bg=CARD2, fg=WHITE, buttonbackground=CARD2,
                   insertbackground=WHITE).pack(side="left", padx=(10, 4))
        self._text(high_row, "%", 11, WHITE, bg=BG).pack(side="left")
        self._text(inner, "Попередження надходять при перетині встановленого порога.",
                   9, MUTED, bg=BG, wraplength=395).pack(anchor="w", pady=(0, 12))''',
'configurable notification UI')

source = replace_once(source,
'''        def save() -> None:
            try:
                set_autostart(autostart.get())''',
'''        def save() -> None:
            try:
                low_value = int(low_pct.get())
                high_value = int(high_pct.get())
            except ValueError:
                messagebox.showerror("Помилка", "Введи ціле число від 1 до 100 для кожного порога.", parent=w)
                return
            if low_value not in range(1, 101) or high_value not in range(1, 101):
                messagebox.showerror("Помилка", "Пороги сповіщень мають бути від 1 до 100%.", parent=w)
                return
            if low_on.get() and high_on.get() and low_value >= high_value:
                messagebox.showerror("Помилка", "Поріг низького заряду має бути меншим за верхній.", parent=w)
                return
            try:
                set_autostart(autostart.get())''',
'validate notification percentages before saving')

source = replace_once(source,
'''            self.settings["alerts"] = alert_on.get()
            save_settings(self.settings)''',
'''            self.settings["alerts"] = low_on.get() or high_on.get()
            self.settings["notify_low"] = low_on.get()
            self.settings["notify_high"] = high_on.get()
            self.settings["low_threshold"] = low_value
            self.settings["high_threshold"] = high_value
            save_settings(self.settings)
            # Avoid treating a changed rule as a freshly crossed threshold.
            self.commands.put(("notification_rules_changed",))''',
'persist user notification preferences')

source = replace_once(source,
'''                elif cmd[0] == "poll" and credentials:
                    if selected_device is None''',
'''                elif cmd[0] == "notification_rules_changed":
                    last_battery = None
                    next_poll = time.monotonic()
                elif cmd[0] == "poll" and credentials:
                    if selected_device is None''',
'new rules reset alert history')

source = replace_once(source,
'''                    if last_battery is not None and self.settings.get("alerts", True):
                        if last_battery > 5 >= value.battery:
                            self.events.put(("notify", "Заряд станції впав до 5% або нижче", value.battery))
                        elif last_battery < 100 == value.battery:
                            self.events.put(("notify", "Станція повністю заряджена", value.battery))''',
'''                    if last_battery is not None:
                        legacy_enabled = bool(self.settings.get("alerts", True))
                        for notice in notification_messages(
                                last_battery, value.battery,
                                low_enabled=bool(self.settings.get("notify_low", legacy_enabled)),
                                low_threshold=int(self.settings.get("low_threshold", 5)),
                                high_enabled=bool(self.settings.get("notify_high", legacy_enabled)),
                                high_threshold=int(self.settings.get("high_threshold", 100))):
                            self.events.put(("notify", notice, value.battery))''',
'custom notification threshold detection')

# No app login, credentials, telemetry, chart, or Android changes.
APP.write_text(source, encoding='utf-8')
print('Windows monitor 1.1: separate custom low/high alarms and outlined white system-tray icon')
