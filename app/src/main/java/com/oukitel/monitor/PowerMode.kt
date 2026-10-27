package com.oukitel.monitor

import android.content.Context
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager

/** Persistent, shared power-mode state for both foreground and background telemetry. */
object PowerMode {
    @Synchronized
    fun update(context: Context, input: Double?, output: Double?, battery: Int?): Pair<String, String> {
        val prefs = context.getSharedPreferences("oukitel", Context.MODE_PRIVATE)
        val previous = prefs.getString("power_mode_v2", "unknown") ?: "unknown"
        if (input == null || output == null) return previous to label(previous)
        // Only observed charging is treated as proof that mains has returned.
        // 0/0 is ambiguous and must never erase a previously observed battery mode.
        val state = when {
            input > output && input > 0.0 -> "charging"
            input == 0.0 && output > 0.0 -> "battery"
            input == 0.0 && output == 0.0 && previous == "battery" -> "battery"
            input == 0.0 && output == 0.0 && battery != null && battery >= 95 && previous in listOf("charging", "mains") -> "mains"
            input == 0.0 && output == 0.0 -> previous
            else -> previous
        }
        if (state != previous) {
            prefs.edit().putString("power_mode_v2", state).apply()
            if (previous != "unknown") {
                if (state == "battery" && prefs.getBoolean("alert_outage", true)) alert(context, "Зникла мережа", battery)
                if (state == "charging" && prefs.getBoolean("alert_charging", true)) alert(context, "Почалось заряджання", battery)
            }
        }
        return state to label(state)
    }

    private fun label(state: String): String = "Режим роботи: " + when (state) {
        "battery" -> "Робота від батареї"
        "charging" -> "Заряджання"
        "mains" -> "Очікування (робота від мережі)"
        else -> "Невідомо"
    }

    private fun alert(context: Context, title: String, battery: Int?) {
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel("charge_alerts", "Сповіщення станції", NotificationManager.IMPORTANCE_HIGH))
        val notification = Notification.Builder(context, "charge_alerts")
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(battery?.let { "Поточний заряд: $it%" } ?: "Стан станції змінився")
            .setAutoCancel(true).build()
        manager.notify((System.currentTimeMillis() % Int.MAX_VALUE).toInt(), notification)
    }
}
