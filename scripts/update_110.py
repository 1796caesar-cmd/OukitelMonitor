"""Oukitel Monitor 1.10: remove the output-voltage block from Home.

Run AFTER update_ui_15.py, update_16.py, update_17.py,
update_18.py and update_19.py. No notification/PowerMode or chart changes.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'app/src/main/java/com/oukitel/monitor/MainActivity.kt'
GRADLE = ROOT / 'app/build.gradle.kts'


def once(source: str, old: str, new: str, description: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f'{description}: expected 1 occurrence, found {count}')
    return source.replace(old, new, 1)


def once_regex(source: str, pattern: str, new: str, description: str) -> str:
    result, count = re.subn(pattern, new, source, count=1, flags=re.MULTILINE)
    if count != 1 or re.search(pattern, result, flags=re.MULTILINE):
        raise RuntimeError(f'{description}: source does not match expected 1.9 version')
    return result


main = MAIN.read_text(encoding='utf-8')
gradle = GRADLE.read_text(encoding='utf-8')

# Remove only the obsolete view. Leave the battery ring and metric cards intact.
main = once(main,
    '    private lateinit var statusText: TextView\n', '',
    'remove obsolete view field')
main = once_regex(main,
    r'^        statusText = text\("Вихідна напруга: —"[^\n]*\n        add\(root, statusText\)\n',
    '',
    'remove complete voltage block from dashboard')
main = once_regex(main,
    r'^        // Use actual measured output voltage; do not substitute the configured 230 V\.\n(?:[^\n]*\n)*?        statusText\.setTextColor\(green\)\n',
    '',
    'remove voltage-only UI update')

# Keep PowerMode.update() and state: they preserve existing grid/outage alerts.
if 'statusText' in main:
    raise RuntimeError('A reference to the removed voltage view still remains')
if 'val state = PowerMode.update(this, t.inputWatts, t.outputWatts, t.battery)' not in main:
    raise RuntimeError('PowerMode must remain in telemetry processing')
if 'checkPowerAlerts(state.first, t.battery)' not in main:
    raise RuntimeError('Expected power alert forwarding was not found')

gradle = once(gradle, 'versionCode = 18', 'versionCode = 19', 'version code')
gradle = once(gradle, 'versionName = "1.9"', 'versionName = "1.10"', 'version name')

MAIN.write_text(main, encoding='utf-8')
GRADLE.write_text(gradle, encoding='utf-8')
print('1.10 ready: voltage panel removed; alerts and charging graph preserved.')
