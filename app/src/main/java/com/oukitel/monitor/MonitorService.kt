package com.oukitel.monitor

import android.app.*
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.Build
import android.content.pm.ServiceInfo
import android.util.Base64
import android.security.keystore.KeyProperties
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean

/** User-visible foreground monitoring. Widget refresh remains manual. */
class MonitorService : Service() {
    private val handler = Handler(Looper.getMainLooper())
    private val busy = AtomicBoolean(false)
    private val prefs by lazy { getSharedPreferences("oukitel", Context.MODE_PRIVATE) }
    private val tick = object : Runnable {
        override fun run() {
            poll()
            handler.postDelayed(this, 60_000L)
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null
    override fun onCreate() {
        super.onCreate()
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel("monitor_active", "Фоновий моніторинг", NotificationManager.IMPORTANCE_LOW))
        nm.createNotificationChannel(NotificationChannel("charge_alerts", "Сповіщення станції", NotificationManager.IMPORTANCE_HIGH))
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val notification = Notification.Builder(this, "monitor_active")
            .setSmallIcon(android.R.drawable.ic_lock_idle_charging)
            .setContentTitle("OukitelMonitor")
            .setContentText("Заряд станції: " + (if (prefs.getInt("previous_level", -1) >= 0) "${prefs.getInt("previous_level", -1)}%" else "—"))
            .setContentIntent(open)
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= 29) startForeground(101, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        else startForeground(101, notification)
        handler.post(tick)
    }
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY
    override fun onDestroy() { handler.removeCallbacks(tick); super.onDestroy() }

    private fun wakeCloud(session: JSONObject) {
        val now = System.currentTimeMillis()
        if (now - prefs.getLong("last_cloud_wake", 0L) < 300_000L) return
        try {
            val payload = JSONObject().apply {
                put("data", "[{\"high_frequency_reporting\":3}]")
                put("deviceList", org.json.JSONArray().put(JSONObject().apply {
                    put("deviceKey", session.getString("dk"))
                    put("productKey", session.getString("pk"))
                }))
                put("cacheTime",60); put("isCache",1); put("isCover",1)
                put("dataFormat",0); put("type",2)
            }
            val c = URL(session.getString("base") + "/v2/binding/enduserapi/batchControlDevice").openConnection() as HttpURLConnection
            try {
                c.requestMethod="POST"; c.connectTimeout=10000; c.readTimeout=12000; c.doOutput=true
                c.setRequestProperty("Authorization",session.getString("token"))
                c.setRequestProperty("Content-Type","application/json")
                c.outputStream.use { it.write(payload.toString().toByteArray(Charsets.UTF_8)) }
                if (c.responseCode in 200..299) {
                    val result=JSONObject(c.inputStream.bufferedReader().use { it.readText() })
                    if (result.optInt("code")==200) prefs.edit().putLong("last_cloud_wake",now).apply()
                }
            } finally { c.disconnect() }
        } catch (_: Exception) { }
    }

    private fun poll() {
        if (!busy.compareAndSet(false, true)) return
        Thread {
            try {
                val encoded = prefs.getString("saved_session", null) ?: return@Thread
                val bytes = Base64.decode(encoded, Base64.NO_WRAP)
                val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
                val key = store.getKey("oukitel_session_v1", null) as? javax.crypto.SecretKey ?: return@Thread
                val cipher = Cipher.getInstance("AES/GCM/NoPadding")
                cipher.init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(128, bytes.copyOfRange(0, 12)))
                val session = JSONObject(String(cipher.doFinal(bytes.copyOfRange(12, bytes.size)), Charsets.UTF_8))
                wakeCloud(session)
                val query = "?pk=" + URLEncoder.encode(session.getString("pk"), "UTF-8") + "&dk=" + URLEncoder.encode(session.getString("dk"), "UTF-8")
                val connection = URL(session.getString("base") + "/v2/binding/enduserapi/getDeviceBusinessAttributes" + query).openConnection() as HttpURLConnection
                val response = try {
                    connection.connectTimeout = 10000
                    connection.readTimeout = 20000
                    connection.setRequestProperty("Authorization", session.getString("token"))
                    connection.setRequestProperty("X-Q-Language", "en")
                    connection.setRequestProperty("quec-random-url", UUID.randomUUID().toString())
                    connection.setRequestProperty("app-info", "[Pixel][Google][raven][33]")
                    if (connection.responseCode !in 200..299) return@Thread
                    JSONObject(connection.inputStream.bufferedReader().use { it.readText() })
                } finally { connection.disconnect() }
                val items = response.optJSONObject("data")?.optJSONArray("customizeTslInfo") ?: return@Thread
                val values = mutableMapOf<Int, Double>()
                for (i in 0 until items.length()) {
                    val item = items.optJSONObject(i) ?: continue
                    item.optString("resourceValce").toDoubleOrNull()?.let { values[item.optInt("abId")] = it }
                }
                val battery = values[1]?.toInt()?.coerceIn(0, 100)
                val input = values[4]
                val output = values[5]
                StatisticsStore.record(this, battery, input, output)
                if (battery != null) {
                    val previous = prefs.getInt("previous_level", -1)
                    if (previous >= 0 && previous != battery) {
                        val rules = org.json.JSONArray(prefs.getString("rules", "[]") ?: "[]")
                        for (i in 0 until rules.length()) {
                            val r = rules.optJSONObject(i) ?: continue
                            if (!r.optBoolean("enabled", true)) continue
                            val limit = r.optInt("threshold", -1)
                            val below = r.optString("kind") == "below"
                            val crossed = if (below) previous >= limit && battery < limit else previous < limit && battery >= limit
                            if (limit in 1..100 && crossed) alert(if (below) "Заряд менше $limit%" else "Заряд досяг $limit%", battery)
                        }
                    }
                    prefs.edit().putInt("previous_level", battery).apply()
                    updateChargeNotification(battery)
                }
                if (input != null && output != null) {
                    PowerMode.update(this, input, output, battery)
                }
            } catch (_: Exception) {
                // Network errors must not be interpreted as a power outage.
            } finally { busy.set(false) }
        }.start()
    }

    private fun updateChargeNotification(level: Int) {
        val open=PendingIntent.getActivity(this,0,Intent(this,MainActivity::class.java),PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val notification=Notification.Builder(this,"monitor_active")
            .setSmallIcon(android.R.drawable.ic_lock_idle_charging)
            .setContentTitle("OukitelMonitor")
            .setContentText("Заряд станції: $level%")
            .setContentIntent(open)
            .setOnlyAlertOnce(true)
            .setOngoing(true)
            .build()
        getSystemService(NotificationManager::class.java).notify(101,notification)
    }

    private fun alert(title: String, level: Int?) {
        val notification = Notification.Builder(this, "charge_alerts")
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(level?.let { "Поточний заряд: $it%" } ?: "Стан станції змінився")
            .setAutoCancel(true)
            .build()
        getSystemService(NotificationManager::class.java).notify((System.currentTimeMillis() % Int.MAX_VALUE).toInt(), notification)
    }

    companion object {
        fun start(context: Context) {
            try {
                val intent = Intent(context, MonitorService::class.java)
                if (Build.VERSION.SDK_INT >= 26) context.startForegroundService(intent)
                else context.startService(intent)
            } catch (_: Exception) { /* Android may block background service starts. */ }
        }
    }
}
