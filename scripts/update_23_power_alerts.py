"""Oukitel Monitor 2.3 — precise one-time grid power notifications.

Run AFTER scripts/update_22_inapp.py. Keeps existing monitoring, battery alerts,
background polling, credentials, GitHub updater and applicationId unchanged.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POWER = ROOT / "app/src/main/java/com/oukitel/monitor/PowerMode.kt"
RULES = ROOT / "app/src/main/java/com/oukitel/monitor/PowerAlertLogic.kt"
MAIN = ROOT / "app/src/main/java/com/oukitel/monitor/MainActivity.kt"
GRADLE = ROOT / "app/build.gradle.kts"
TEST = ROOT / "app/src/test/java/com/oukitel/monitor/PowerAlertLogicTest.kt"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


if RULES.exists() or TEST.exists():
    raise RuntimeError("Power-alert 2.3 patch already applied; refusing duplicate modification")

power = POWER.read_text(encoding="utf-8")
main = MAIN.read_text(encoding="utf-8")
gradle = GRADLE.read_text(encoding="utf-8")

old_logic = '''        if (state != previous) {
            prefs.edit().putString("power_mode_v2", state).apply()
            if (previous != "unknown") {
                if (state == "battery" && prefs.getBoolean("alert_outage", true)) alert(context, "Зникла мережа", battery)
                if (state == "charging" && prefs.getBoolean("alert_charging", true)) alert(context, "Почалось заряджання", battery)
            }
        }
        return state to label(state)'''
new_logic = '''        // The visual mode remains separate from power-outage notifications.
        if (state != previous) {
            prefs.edit().putString("power_mode_v2", state).apply()
        }

        // The same persisted alert state is shared by the foreground Activity
        // and the background MonitorService. @Synchronized prevents races.
        // Ambiguous telemetry does not reset it or generate duplicate alerts.
        val observed = PowerAlertLogic.detect(input, output, battery)
        if (observed != null) {
            val prior = prefs.getString("power_alert_state_v3", "unknown") ?: "unknown"
            if (prior != observed) {
                prefs.edit().putString("power_alert_state_v3", observed).apply()
                when (PowerAlertLogic.event(prior, observed)) {
                    PowerAlertLogic.EVENT_OUTAGE -> if (prefs.getBoolean("alert_outage", true)) {
                        alert(context, "Зникло світло", battery)
                    }
                    PowerAlertLogic.EVENT_RESTORED -> if (prefs.getBoolean("alert_charging", true)) {
                        alert(context, "Світло з'явилося", battery)
                    }
                }
            }
        }
        return state to label(state)'''
power = replace_once(power, old_logic, new_logic, "replace previous power notifications")
main = replace_once(main, 'systemToggle("⚡ Почалось заряджання","alert_charging")',
                    'systemToggle("⚡ Світло з’явилося","alert_charging")', "restoration toggle label")
main = replace_once(main, 'systemToggle("🔌 Зникла мережа","alert_outage")',
                    'systemToggle("🔌 Зникло світло","alert_outage")', "outage toggle label")
gradle = replace_once(gradle, 'versionName = "2.2"', 'versionName = "2.3"', "new version name")
gradle = replace_once(gradle,
    '    implementation("androidx.core:core:1.15.0")',
    '    implementation("androidx.core:core:1.15.0")\n    testImplementation("junit:junit:4.13.2")',
    'unit-test dependency')

rules = '''package com.oukitel.monitor

/** Single source of truth for outage and restoration signal detection.
 *  Null means the snapshot is ambiguous: keep the last confirmed state.
 */
object PowerAlertLogic {
    const val OUTAGE = "outage"
    const val MAINS = "mains"
    const val EVENT_OUTAGE = "outage_event"
    const val EVENT_RESTORED = "restored_event"

    fun detect(input: Double?, output: Double?, battery: Int?): String? {
        if (input == null || output == null || !input.isFinite() || !output.isFinite()) return null
        if (input < 0.0 || output < 0.0) return null
        // Both input/output MUST be real readings, and battery MUST be known.
        if (input == 0.0 && output > 0.0 && battery != null && battery in 0..94) return OUTAGE
        if (input > output) return MAINS
        return null
    }

    fun event(previous: String, observed: String): String? = when {
        observed == OUTAGE && previous != OUTAGE -> EVENT_OUTAGE
        observed == MAINS && previous == OUTAGE -> EVENT_RESTORED
        else -> null
    }
}
'''

unit_tests = '''package com.oukitel.monitor

import org.junit.Assert.*
import org.junit.Test

class PowerAlertLogicTest {
    @Test fun outageRequiresAllThreeConditions() {
        assertEquals(PowerAlertLogic.OUTAGE, PowerAlertLogic.detect(0.0, 60.0, 94))
        assertEquals(PowerAlertLogic.OUTAGE, PowerAlertLogic.detect(0.0, 200.0, 1))
        assertNull(PowerAlertLogic.detect(0.0, 60.0, 95))
        assertNull(PowerAlertLogic.detect(0.0, 60.0, 100))
        assertNull(PowerAlertLogic.detect(0.0, 0.0, 40))
        assertNull(PowerAlertLogic.detect(5.0, 60.0, 40))
        assertNull(PowerAlertLogic.detect(0.0, 60.0, null))
        assertNull(PowerAlertLogic.detect(null, 60.0, 70))
    }

    @Test fun restorationRequiresInputGreaterThanOutput() {
        assertEquals(PowerAlertLogic.MAINS, PowerAlertLogic.detect(101.0, 100.0, 80))
        assertEquals(PowerAlertLogic.MAINS, PowerAlertLogic.detect(400.0, 0.0, 99))
        assertNull(PowerAlertLogic.detect(100.0, 100.0, 80))
        assertNull(PowerAlertLogic.detect(0.0, 50.0, 95))
    }

    @Test fun repeatedStateNeverSendsRepeatedMessages() {
        assertEquals(PowerAlertLogic.EVENT_OUTAGE, PowerAlertLogic.event("unknown", PowerAlertLogic.OUTAGE))
        assertNull(PowerAlertLogic.event(PowerAlertLogic.OUTAGE, PowerAlertLogic.OUTAGE))
        assertEquals(PowerAlertLogic.EVENT_RESTORED, PowerAlertLogic.event(PowerAlertLogic.OUTAGE, PowerAlertLogic.MAINS))
        assertNull(PowerAlertLogic.event(PowerAlertLogic.MAINS, PowerAlertLogic.MAINS))
        assertNull(PowerAlertLogic.event("unknown", PowerAlertLogic.MAINS))
        assertEquals(PowerAlertLogic.EVENT_OUTAGE, PowerAlertLogic.event(PowerAlertLogic.MAINS, PowerAlertLogic.OUTAGE))
    }
}
'''

# Save only after all expected source structures have been confirmed.
POWER.write_text(power, encoding="utf-8")
MAIN.write_text(main, encoding="utf-8")
GRADLE.write_text(gradle, encoding="utf-8")
RULES.write_text(rules, encoding="utf-8")
TEST.parent.mkdir(parents=True, exist_ok=True)
TEST.write_text(unit_tests, encoding="utf-8")
print("OukitelMonitor 2.3: grid outage input=0, output>0, SOC<95%; restored when input>output; single alerts")
