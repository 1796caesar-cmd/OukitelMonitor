"""OukitelMonitor 1.7 patch, applied AFTER update_ui_15.py and update_16.py.

- Show measured AC output voltage from ac_data/ac1_output_voltage, not the
  output-voltage SETTING (ACvoltage_Switchover, id 28).
- Connect all real battery-history samples, even if reports are hours apart.
- Preserve existing PowerMode notifications and alert rules unchanged.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'app/src/main/java/com/oukitel/monitor/MainActivity.kt'
STAT = ROOT / 'app/src/main/java/com/oukitel/monitor/Statistics.kt'
GRADLE = ROOT / 'app/build.gradle.kts'


def replace_once(source: str, old: str, new: str, title: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f'{title}: expected exactly 1 match; found {count}: {old[:90]!r}')
    return source.replace(old, new, 1)


# Validate all inputs BEFORE modifying any files.
main = MAIN.read_text(encoding='utf-8')
stats = STAT.read_text(encoding='utf-8')
gradle = GRADLE.read_text(encoding='utf-8')

main = replace_once(
    main, '"Режим роботи: Невідомо", 19f',
    '"Вихідна напруга: —", 19f',
    'dashboard voltage title',
)

# Keep PowerMode.update(): it is responsible for power-related NOTIFICATIONS,
# even though its label is no longer shown on the dashboard.
main = replace_once(
    main,
    '        val state = PowerMode.update(this, t.inputWatts, t.outputWatts, t.battery)',
    '        val state = PowerMode.update(this, t.inputWatts, t.outputWatts, t.battery)',
    'preserve PowerMode alerts',
)

status_line = re.compile(r'(?m)^        statusText\.text = if \(state\.first == "mains"\) .* else state\.second$')
if len(status_line.findall(main)) != 1:
    raise RuntimeError('Voltage display: expected the 1.5 statusText line after the 1.6 patch')
main = status_line.sub(
    '''        // Use actual measured output voltage; do not substitute the configured 230 V.
        val outputVoltage = t.acVoltage
        val displayVoltage = outputVoltage?.let {
            if (it % 1.0 == 0.0) it.toInt().toString()
            else String.format(Locale.getDefault(), "%.1f", it)
        } ?: "—"
        statusText.text = "Вихідна напруга: $displayVoltage" + if (outputVoltage != null) " В" else ""
'''.rstrip('\n'), main, count=1)
main = replace_once(
    main,
    '        statusText.setTextColor(if (state.first == "battery") Color.rgb(255, 112, 112) else green)',
    '        statusText.setTextColor(green)',
    'voltage label color',
)

main = replace_once(
    main,
    'val inputWatts: Double?, val outputWatts: Double?)',
    'val inputWatts: Double?, val outputWatts: Double?, val acVoltage: Double?)',
    'telemetry model',
)

# The cloud API represents STRUCT properties in different ways depending on
# firmware/endpoint: an object, JSON-encoded string or an array of values.
# Parse only the actual ac1_output_voltage attribute; id 28 is a SETPOINT.
voltage_parser = r'''        // Value reported by the station for its AC output (not voltage setting).
        fun parseVoltageValue(raw: Any?): Double? {
            val number = when (raw) {
                is Number -> raw.toDouble()
                is String -> raw.trim().removeSuffix("V").trim().toDoubleOrNull()
                is JSONObject -> {
                    val value = raw.opt("value") ?: raw.opt("resourceValce")
                    when (value) {
                        is Number -> value.toDouble()
                        is String -> value.trim().removeSuffix("V").trim().toDoubleOrNull()
                        else -> null
                    }
                }
                else -> null
            }
            return number?.takeIf { it.isFinite() && it >= 0.0 && it <= 300.0 }
        }

        fun findAcVoltage(raw: Any?, depth: Int = 0): Double? {
            if (depth > 6 || raw == null || raw == JSONObject.NULL) return null
            return when (raw) {
                is JSONObject -> {
                    if (raw.has("ac1_output_voltage")) {
                        parseVoltageValue(raw.opt("ac1_output_voltage"))
                            ?: findAcVoltage(raw.opt("ac1_output_voltage"), depth + 1)
                    } else if (listOf("code", "abCode", "attributeCode", "propertyCode")
                            .any { raw.optString(it) == "ac1_output_voltage" }) {
                        parseVoltageValue(raw.opt("resourceValce"))
                            ?: parseVoltageValue(raw.opt("value"))
                    } else {
                        var found: Double? = null
                        for (key in listOf("ac_data", "data", "value", "resourceValce", "properties", "attributes")) {
                            if (raw.has(key)) {
                                found = findAcVoltage(raw.opt(key), depth + 1)
                                if (found != null) break
                            }
                        }
                        found
                    }
                }
                is org.json.JSONArray -> {
                    var found: Double? = null
                    for (index in 0 until raw.length()) {
                        found = findAcVoltage(raw.opt(index), depth + 1)
                        if (found != null) break
                    }
                    found
                }
                is String -> {
                    val value = raw.trim()
                    when {
                        value.startsWith("{") -> runCatching { findAcVoltage(JSONObject(value), depth + 1) }.getOrNull()
                        value.startsWith("[") -> runCatching { findAcVoltage(org.json.JSONArray(value), depth + 1) }.getOrNull()
                        else -> null
                    }
                }
                else -> null
            }
        }
        var acOutputVoltage: Double? = null
        for (index in 0 until items.length()) {
            val item = items.optJSONObject(index) ?: continue
            val code = listOf("abCode", "attributeCode", "propertyCode", "code")
                .map { item.optString(it) }
                .firstOrNull { it == "ac_data" || it == "ac1_output_voltage" }
            val raw = item.opt("resourceValce")
            acOutputVoltage = when {
                code == "ac1_output_voltage" -> parseVoltageValue(raw)
                item.optInt("abId", -1) == 6 || code == "ac_data" ||
                    item.optString("resourceValce").contains("ac1_output_voltage") -> findAcVoltage(raw)
                else -> null
            }
            if (acOutputVoltage != null) break
        }
'''
main = replace_once(
    main,
    '        fun number(tag: Int): Double? = values[tag]?.toDoubleOrNull()',
    voltage_parser + '        fun number(tag: Int): Double? = values[tag]?.toDoubleOrNull()',
    'parse live AC voltage',
)
main = replace_once(
    main,
    'fmt(14, "°C"), remaining, input, output)',
    'fmt(14, "°C"), remaining, input, output, acOutputVoltage)',
    'telemetry response',
)

# 1.6 left the display modes and battery-only statistics intact. 1.7 just
# connects successive REAL samples; no artificial data points are inserted.
stats = replace_once(
    stats,
    'if (lastT==null || e.timestamp-lastT>35*60*1000L) path.moveTo(xx,yy) else path.lineTo(xx,yy)',
    'if (lastT == null) path.moveTo(xx, yy) else path.lineTo(xx, yy)',
    'connect sparse charge history',
)

main = replace_once(
    main,
    'Записи зберігаються не частіше ніж раз на 15 хвилин. Пропущені вимірювання не домальовуються.',
    'Лінія з’єднує всі збережені точки заряду навіть після перерв у зв’язку. Проміжні показники не вимірювалися.',
    'explain interpolated chart segments',
)

gradle = replace_once(gradle, 'versionCode = 15', 'versionCode = 16', 'version code')
gradle = replace_once(gradle, 'versionName = "1.6"', 'versionName = "1.7"', 'version name')

MAIN.write_text(main, encoding='utf-8')
STAT.write_text(stats, encoding='utf-8')
GRADLE.write_text(gradle, encoding='utf-8')
print('OukitelMonitor 1.7 applied: real AC voltage if exposed; continuous charge line; alerts untouched')
