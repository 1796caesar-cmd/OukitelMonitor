"""Oukitel Monitor 1.9 — keep the ongoing notification synchronized with UI.

Apply after update_ui_15, update_16, update_17, update_18.
Only touches the UI's charge-notification synchronization and prevents a
separately scheduled background poll from overwriting fresh foreground data.
Existing charge threshold rules, network-power alerts and PowerMode remain intact.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "app/src/main/java/com/oukitel/monitor/MainActivity.kt"
SERVICE = ROOT / "app/src/main/java/com/oukitel/monitor/MonitorService.kt"
GRADLE = ROOT / "app/build.gradle.kts"


def replace_once(source, old, new, label):
    matches = source.count(old)
    if matches != 1:
        raise RuntimeError(f"{label}: expected exactly 1 match; got {matches}: {old[:110]!r}")
    return source.replace(old, new, 1)


main = MAIN.read_text(encoding="utf-8")
service = SERVICE.read_text(encoding="utf-8")
gradle = GRADLE.read_text(encoding="utf-8")

# Activity visibility is recorded by the UI and cleared upon pausing so the
# background service can resume notification ownership when app is minimized.
main = replace_once(main,
    '    override fun onPause() { super.onPause(); handler.removeCallbacks(tick); handler.removeCallbacks(freshnessTick) }',
    '''    override fun onPause() {
        prefs().edit().putBoolean("ui_dashboard_visible", false).apply()
        super.onPause()
        handler.removeCallbacks(tick)
        handler.removeCallbacks(freshnessTick)
    }''', 'clear visibility onPause')
main = replace_once(main,
    '    override fun onResume() { super.onResume(); if (active && currentScreen == "dashboard") { loadData(); scheduleForeground(); scheduleFreshness() } }',
    '''    override fun onResume() {
        super.onResume()
        prefs().edit().putBoolean("ui_dashboard_visible", active && currentScreen == "dashboard").apply()
        if (active && currentScreen == "dashboard") {
            loadData()
            scheduleForeground()
            scheduleFreshness()
        }
    }''', 'restore visibility onResume')

# Opening another app screen means the live battery value is no longer visible.
for screen in ["login", "settings", "alerts", "statistics"]:
    main = replace_once(main,
        f'        currentScreen = "{screen}"',
        f'        currentScreen = "{screen}"\n        prefs().edit().putBoolean("ui_dashboard_visible", false).apply()',
        f'visibility when opening {screen}')
main = replace_once(main,
    '''        currentScreen = "dashboard"
        active = true''',
    '''        currentScreen = "dashboard"
        active = true
        prefs().edit().putBoolean("ui_dashboard_visible", true).apply()''',
    'visibility when opening dashboard')

# The status shade's persistent notification is owned by MonitorService (ID 101).
# Replacing that SAME notification after an actual successful UI fetch is safe:
# it doesn't send an alarm or change the charging/outage detection state.
notification_sync_method = '''    private fun synchronizeChargeNotification(level: Int?) {
        if (level == null || !prefs().getBoolean("background_refresh_enabled", true)) return
        val manager = getSystemService(NotificationManager::class.java)
        // If the background monitor is off or has not started, do not post a
        // phantom permanent notification from the Activity.
        if (manager.activeNotifications.none { it.id == 101 }) return
        val open = android.app.PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            android.app.PendingIntent.FLAG_UPDATE_CURRENT or android.app.PendingIntent.FLAG_IMMUTABLE
        )
        val notification = android.app.Notification.Builder(this, "monitor_active")
            .setSmallIcon(android.R.drawable.ic_lock_idle_charging)
            .setContentTitle("OukitelMonitor")
            .setContentText("Заряд станції: $level%")
            .setContentIntent(open)
            .setOnlyAlertOnce(true)
            .setOngoing(true)
            .build()
        manager.notify(101, notification)
    }

'''
main = replace_once(main,
    '    private fun applyTelemetry(t: Telemetry) {',
    notification_sync_method + '    private fun applyTelemetry(t: Telemetry) {',
    'add notification sync method')
main = replace_once(main,
    '''        saveTelemetry(t)
        StatisticsStore.record(this, t.battery, t.inputWatts, t.outputWatts)''',
    '''        saveTelemetry(t)
        if (t.battery != null) {
            // Share the successful read with the background service. Never
            // publish an old or speculative battery percentage here.
            prefs().edit().putLong("ui_charge_fetched_ms", System.currentTimeMillis()).apply()
            synchronizeChargeNotification(t.battery)
        }
        StatisticsStore.record(this, t.battery, t.inputWatts, t.outputWatts)''',
    'update notification immediately after successful UI charge fetch')

# The background worker may finish an older, independently started cloud read
# after a newer UI read. While the dashboard is visible and its reading is
# fresh, leave the ongoing notification alone. Background alerts are unchanged.
service = replace_once(service,
    '''                    updateChargeNotification(battery)''',
    '''                    val uiChargeMs = prefs.getLong("ui_charge_fetched_ms", 0L)
                    val dashboardHasFreshCharge = prefs.getBoolean("ui_dashboard_visible", false) &&
                        uiChargeMs > 0L &&
                        System.currentTimeMillis() - uiChargeMs in 0L..120_000L
                    if (!dashboardHasFreshCharge) updateChargeNotification(battery)''',
    'avoid stale background notification over fresh visible UI')

gradle = replace_once(gradle, 'versionCode = 17', 'versionCode = 18', 'version code 1.9')
gradle = replace_once(gradle, 'versionName = "1.8"', 'versionName = "1.9"', 'version name 1.9')

MAIN.write_text(main, encoding="utf-8")
SERVICE.write_text(service, encoding="utf-8")
GRADLE.write_text(gradle, encoding="utf-8")
print('Oukitel Monitor 1.9: status-shade charge updates immediately with UI; previous alerts untouched.')
