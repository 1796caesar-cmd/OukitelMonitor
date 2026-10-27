package com.oukitel.monitor

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.widget.RemoteViews
import android.util.Base64
import android.security.keystore.KeyProperties
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID

class MonitorWidget : AppWidgetProvider() {
    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        ids.forEach { update(context, manager, it) }
    }
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == ACTION_REFRESH) {
            val pending = goAsync()
            Thread {
                try { refreshFromCloud(context.applicationContext) }
                finally { pending.finish() }
            }.start()
        } else super.onReceive(context, intent)
    }

    companion object {
        private const val ACTION_REFRESH = "com.oukitel.monitor.REFRESH_WIDGET"

        private fun refreshFromCloud(context: Context) {
            val prefs = context.getSharedPreferences("oukitel", Context.MODE_PRIVATE)
            try {
                val encoded = prefs.getString("saved_session", null) ?: throw IllegalStateException("Увійдіть у застосунок один раз")
                val bytes = Base64.decode(encoded, Base64.NO_WRAP)
                val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
                val key = store.getKey("oukitel_session_v1", null) as? javax.crypto.SecretKey
                    ?: throw IllegalStateException("Авторизація недоступна")
                val cipher = Cipher.getInstance("AES/GCM/NoPadding")
                cipher.init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(128, bytes.copyOfRange(0,12)))
                val session = JSONObject(String(cipher.doFinal(bytes.copyOfRange(12, bytes.size)), Charsets.UTF_8))
                val query = "?pk=" + URLEncoder.encode(session.getString("pk"), "UTF-8") + "&dk=" + URLEncoder.encode(session.getString("dk"), "UTF-8")
                val url = URL(session.getString("base") + "/v2/binding/enduserapi/getDeviceBusinessAttributes" + query)
                val connection = url.openConnection() as HttpURLConnection
                val response = try {
                    connection.connectTimeout = 7000
                    connection.readTimeout = 7000
                    connection.setRequestProperty("Authorization", session.getString("token"))
                    connection.setRequestProperty("X-Q-Language", "en")
                    connection.setRequestProperty("quec-random-url", UUID.randomUUID().toString())
                    connection.setRequestProperty("app-info", "[Pixel][Google][raven][33]")
                    JSONObject(connection.inputStream.bufferedReader().use { it.readText() })
                } finally { connection.disconnect() }
                val items = response.optJSONObject("data")?.optJSONArray("customizeTslInfo")
                    ?: throw IllegalStateException("Немає показників")
                val values = mutableMapOf<Int, Double>()
                for (i in 0 until items.length()) {
                    val item = items.optJSONObject(i) ?: continue
                    item.optString("resourceValce").toDoubleOrNull()?.let { values[item.optInt("abId")] = it }
                }
                if (values[1] == null) throw IllegalStateException("Заряд не отримано")
                fun formatted(tag: Int, unit: String) = values[tag]?.let { "${it.toInt()} $unit" } ?: "—"
                val input = values[4] ?: 0.0
                val output = values[5] ?: 0.0
                val remaining = if (output > input) values[2]?.toLong()?.takeIf { it >= 0 }?.let { "${it/60} год ${it%60} хв" } ?: "—" else "—"
                prefs.edit().putInt("charge", values[1]!!.toInt().coerceIn(0,100))
                    .putString("input",formatted(4,"Вт")).putString("output",formatted(5,"Вт"))
                    .putString("temp",formatted(14,"°C")).putString("remaining",remaining)
                    .putString("updated",SimpleDateFormat("HH:mm:ss",Locale.getDefault()).format(Date()))
                    .apply()
            } catch (e: Exception) {
                prefs.edit().putString("updated", "Помилка оновлення").apply()
            }
            updateAll(context)
        }

        fun updateAll(context: Context) {
            val manager=AppWidgetManager.getInstance(context)
            val ids=manager.getAppWidgetIds(ComponentName(context,MonitorWidget::class.java))
            ids.forEach { update(context,manager,it) }
        }
        private fun update(context: Context, manager: AppWidgetManager, id: Int) {
            val p=context.getSharedPreferences("oukitel",Context.MODE_PRIVATE)
            val views=RemoteViews(context.packageName,R.layout.monitor_widget)
            val charge=p.getInt("charge",-1)
            views.setTextViewText(R.id.widget_charge,if(charge>=0) "$charge%" else "—%")
            views.setTextViewText(R.id.widget_input,"Вхід: ${p.getString("input","—")}")
            views.setTextViewText(R.id.widget_output,"Вихід: ${p.getString("output","—")}")
            views.setTextViewText(R.id.widget_temp,"Температура: ${p.getString("temp","—")}")
            views.setTextViewText(R.id.widget_time,"Час роботи: ${p.getString("remaining","—")}")
            views.setTextViewText(R.id.widget_updated,"Оновлено: ${p.getString("updated","—")}")
            val intent=Intent(context,MainActivity::class.java)
            views.setOnClickPendingIntent(R.id.widget_root,PendingIntent.getActivity(context,0,intent,PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE))
            val refreshIntent = Intent(context, MonitorWidget::class.java).apply { action = ACTION_REFRESH }
            views.setOnClickPendingIntent(R.id.widget_refresh,PendingIntent.getBroadcast(context,1,refreshIntent,PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE))
            manager.updateAppWidget(id,views)
        }
    }
}
