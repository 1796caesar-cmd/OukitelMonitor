"""OukitelMonitor 2.5 — today's planned outages by selected address and queue.

Apply after update_24_chart_zoom.py. The selected street/house stays on-device;
only the queue is used to request an independent public schedule dataset.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'app/src/main/java/com/oukitel/monitor/MainActivity.kt'
SCHEDULE = ROOT / 'app/src/main/java/com/oukitel/monitor/OutageSchedule.kt'
GRADLE = ROOT / 'app/build.gradle.kts'


def one(src: str, before: str, after: str, label: str) -> str:
    count = src.count(before)
    if count != 1:
        raise RuntimeError(f'{label}: expected one match, found {count}')
    return src.replace(before, after, 1)

if SCHEDULE.exists():
    raise RuntimeError('OutageSchedule.kt already exists; do not apply 2.5 patch twice')

main = MAIN.read_text(encoding='utf-8')
gradle = GRADLE.read_text(encoding='utf-8')

main = one(main,
'''    private lateinit var refresh: TextView
''',
'''    private lateinit var refresh: TextView
    private var outageStatus: TextView? = null
''', 'dashboard label field')

main = one(main,
'''        batteryText = batteryView.percent
''',
'''        batteryText = batteryView.percent
        showOutagePanel(root)
''', 'position outage panel right below battery ring')

main = one(main,
'''        addBackgroundSettings(root)
        gap(root,26)
''',
'''        addBackgroundSettings(root)
        gap(root,26)
        addOutageSettings(root)
        gap(root,26)
''', 'outage settings section')

methods = r'''    // The selected address is only an on-device label. Its queue must be
    // verified through the operator's official address lookup first.
    private fun addOutageSettings(root: LinearLayout) {
        add(root, text("Графік відключень", 19f, white, true)); gap(root, 9)
        val p = prefs()
        val switchRow = row().apply {
            gravity = Gravity.CENTER_VERTICAL
            background = shape(panel, 18, green)
            setPadding(dp(13), dp(12), dp(10), dp(12))
        }
        switchRow.addView(text("Відображати графік відключень на сьогодні", 15f, white, true),
            LinearLayout.LayoutParams(0, -2, 1f))
        val enabled = Switch(this).apply { isChecked = p.getBoolean("show_outage_schedule", false) }
        switchRow.addView(enabled)
        add(root, switchRow); gap(root, 12)
        add(root, text("Адреса", 15f, white, true)); gap(root, 5)
        val address = EditText(this).apply {
            hint = "Місто, вулиця, номер будинку"
            setText(p.getString("outage_address", ""))
            setTextColor(white); setHintTextColor(muted)
            setSingleLine(true)
            background = shape(panel, 14)
            setPadding(dp(14), dp(12), dp(14), dp(12))
        }
        add(root, address); gap(root, 11)
        add(root, text("Підчерга цієї адреси", 15f, white, true)); gap(root, 6)
        val groups = arrayOf("Оберіть підчергу", "1.1", "1.2", "2.1", "2.2", "3.1", "3.2", "4.1", "4.2", "5.1", "5.2", "6.1", "6.2")
        val spinner = Spinner(this)
        spinner.adapter = object : ArrayAdapter<String>(this, android.R.layout.simple_spinner_dropdown_item, groups) {
            override fun getView(position: Int, convertView: View?, parent: android.view.ViewGroup): View =
                super.getView(position, convertView, parent).also { (it as? TextView)?.setTextColor(white); it.setPadding(dp(13), dp(10), dp(13), dp(10)) }
            override fun getDropDownView(position: Int, convertView: View?, parent: android.view.ViewGroup): View =
                super.getDropDownView(position, convertView, parent).also { (it as? TextView)?.setTextColor(Color.rgb(30, 43, 50)) }
        }
        spinner.background = shape(palette.tile, 16, green)
        val index = groups.indexOf(p.getString("outage_group", ""))
        spinner.setSelection(index.coerceAtLeast(0))
        add(root, spinner); gap(root, 8)
        add(root, text("Вкажи адресу та підчергу, визначену за цією адресою на сайті Житомиробленерго. Черги іноді змінюються.", 12f, muted)); gap(root, 10)
        val lookup = text("↗   Знайти підчергу за адресою", 15f, green, true).apply {
            background = shape(panel, 16, green)
            setPadding(dp(13), dp(13), dp(13), dp(13))
            setOnClickListener {
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://www.ztoe.com.ua/unhooking-search.php")))
            }
        }
        add(root, lookup); gap(root, 10)
        val save = text("✓   Зберегти графік відключень", 16f, white, true).apply {
            background = shape(palette.tile, 16, green)
            gravity = Gravity.CENTER
            setPadding(dp(14), dp(14), dp(14), dp(14))
            setOnClickListener {
                val location = address.text.toString().trim()
                val group = groups[spinner.selectedItemPosition]
                if (enabled.isChecked && (location.isEmpty() || spinner.selectedItemPosition == 0)) {
                    Toast.makeText(this@MainActivity, "Вкажи адресу та підчергу", Toast.LENGTH_LONG).show()
                } else {
                    val oldGroup = p.getString("outage_group", "")
                    p.edit().putBoolean("show_outage_schedule", enabled.isChecked)
                        .putString("outage_address", location)
                        .putString("outage_group", if (spinner.selectedItemPosition == 0) "" else group)
                        .apply()
                    if (oldGroup != group) p.edit().remove("outage_cache_json").remove("outage_cache_group")
                        .remove("outage_cache_fetched").apply()
                    Toast.makeText(this@MainActivity, "Налаштування збережено", Toast.LENGTH_SHORT).show()
                }
            }
        }
        add(root, save)
    }

    private fun showOutagePanel(root: LinearLayout) {
        outageStatus = null
        if (!prefs().getBoolean("show_outage_schedule", false)) return
        val box = column().apply {
            background = shape(panel, 20, green)
            setPadding(dp(15), dp(13), dp(15), dp(13))
        }
        val header = row().apply { gravity = Gravity.CENTER_VERTICAL }
        val group = prefs().getString("outage_group", "") ?: ""
        header.addView(text("⚡ Відключення сьогодні" + if (group.isNotBlank()) " · $group" else "", 16f, white, true),
            LinearLayout.LayoutParams(0, -2, 1f))
        val refreshSchedule = text("⟳ Оновити", 13f, green, true).apply {
            setPadding(dp(10), dp(2), dp(5), dp(2))
            contentDescription = "Оновити графік відключень"
        }
        header.addView(refreshSchedule)
        add(box, header)
        val location = prefs().getString("outage_address", "").orEmpty()
        if (location.isNotBlank()) {
            gap(box, 3); add(box, text(location, 12f, muted))
        }
        gap(box, 7)
        val state = text("Отримання графіка…", 15f, white, true)
        add(box, state)
        outageStatus = state
        refreshSchedule.setOnClickListener { updateOutages(state, true) }
        add(root, box); gap(root, 10)
        updateOutages(state, false)
    }

    private fun updateOutages(label: TextView, force: Boolean) {
        val p = prefs()
        val group = p.getString("outage_group", "").orEmpty()
        if (!OutageSchedule.VALID_GROUPS.contains(group)) {
            label.text = "Обери адресу й підчергу в налаштуваннях"
            return
        }
        val cached = p.getString("outage_cache_json", null)
        val cachedGroup = p.getString("outage_cache_group", "")
        var usableCache = false
        if (cached != null && cachedGroup == group) {
            try {
                label.text = OutageSchedule.parse(cached, group).display + "\nЗбережений графік"
                usableCache = true
            } catch (_: Exception) { /* A new day invalidates yesterday's data. */ }
        }
        val fetched = p.getLong("outage_cache_fetched", 0L)
        val needsRefresh = force || !usableCache || System.currentTimeMillis() - fetched > 30L * 60L * 1000L
        if (!needsRefresh) return
        if (force || !usableCache) label.text = "Оновлення графіка…"
        Thread {
            try {
                val json = OutageSchedule.download()
                val result = OutageSchedule.parse(json, group)
                p.edit().putString("outage_cache_json", json).putString("outage_cache_group", group)
                    .putLong("outage_cache_fetched", System.currentTimeMillis()).apply()
                runOnUiThread {
                    if (currentScreen == "dashboard" && outageStatus === label &&
                        prefs().getString("outage_group", "") == group) {
                        label.text = result.display
                    }
                }
            } catch (e: Exception) {
                runOnUiThread {
                    if (currentScreen == "dashboard" && outageStatus === label) {
                        label.text = (if (usableCache) label.text.toString() else "Графік недоступний") +
                            "\nНе вдалося оновити: ${e.message ?: "помилка мережі"}"
                    }
                }
            }
        }.start()
    }

'''

main = one(main, '    private fun showSettings() {', methods + '    private fun showSettings() {', 'add outage UI and update actions')
gradle = one(gradle, 'versionName = "2.4"', 'versionName = "2.5"', 'bump version')
MAIN.write_text(main, encoding='utf-8')
GRADLE.write_text(gradle, encoding='utf-8')

SCHEDULE.write_text(r'''package com.oukitel.monitor

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/** Only published planned power-outage windows; no real-time grid-state assumptions. */
object OutageSchedule {
    val VALID_GROUPS = setOf("1.1", "1.2", "2.1", "2.2", "3.1", "3.2", "4.1", "4.2", "5.1", "5.2", "6.1", "6.2")
    // Independent public mirror/parser of the power operator's schedule,
    // not an undocumented internal interface of the Svitlochek application.
    private const val DATA_URL = "https://raw.githubusercontent.com/yaroslav2901/OE_OUTAGE_DATA/main/data/Zhytomyroblenergo.json"
    private val kyiv = TimeZone.getTimeZone("Europe/Kyiv")
    data class Window(val startMinutes: Int, val endMinutes: Int, val tentative: Boolean)
    data class Result(val display: String, val windows: List<Window>, val sourceUpdated: String)

    fun download(): String {
        val conn = URL(DATA_URL).openConnection() as HttpURLConnection
        return try {
            conn.requestMethod = "GET"
            conn.connectTimeout = 12000
            conn.readTimeout = 15000
            conn.setRequestProperty("User-Agent", "OukitelMonitor/2.5")
            conn.setRequestProperty("Cache-Control", "no-cache")
            if (conn.responseCode !in 200..299) error("HTTP ${conn.responseCode}")
            conn.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
        } finally { conn.disconnect() }
    }

    private fun minutes(value: String): Int {
        val part = value.split(":")
        require(part.size == 2)
        val hh = part[0].toInt()
        val mm = part[1].toInt()
        require(hh in 0..24 && mm in 0..59 && (hh < 24 || mm == 0))
        return hh * 60 + mm
    }
    private fun clock(value: Int) = "%02d:%02d".format(Locale.US, value / 60, value % 60)
    private fun dateKey(timestampMillis: Long) = SimpleDateFormat("yyyy-MM-dd", Locale.US).apply { timeZone = kyiv }.format(Date(timestampMillis))

    /** Refuses stale/malformed schedules rather than presenting invented free hours. */
    fun parse(json: String, group: String, now: Long = System.currentTimeMillis()): Result {
        require(group in VALID_GROUPS) { "Невідома підчерга" }
        val root = JSONObject(json)
        require(root.optString("regionId") == "Zhytomyr") { "Неправильний регіон" }
        val fact = root.getJSONObject("fact")
        val today = fact.getLong("today")
        require(dateKey(today * 1000) == dateKey(now)) { "Графік ще не оновлено на сьогодні" }
        val queue = fact.getJSONObject("data").getJSONObject(today.toString()).getJSONObject("GPV$group")
        val zones = root.getJSONObject("preset").getJSONObject("time_zone")
        val segments = mutableListOf<Window>()
        for (hour in 1..24) {
            val zone = zones.getJSONArray(hour.toString())
            val a = minutes(zone.getString(1))
            val b = minutes(zone.getString(2))
            require(b - a == 60) { "Невірний часовий інтервал" }
            val code = queue.getString(hour.toString())
            when (code) {
                "yes" -> Unit
                "no" -> segments.add(Window(a, b, false))
                "first" -> segments.add(Window(a, a + 30, false))
                "second" -> segments.add(Window(a + 30, b, false))
                "maybe" -> segments.add(Window(a, b, true))
                else -> error("Невідомий стан графіка: $code")
            }
        }
        val merged = mutableListOf<Window>()
        for (segment in segments) {
            val last = merged.lastOrNull()
            if (last != null && last.endMinutes == segment.startMinutes && last.tentative == segment.tentative)
                merged[merged.lastIndex] = last.copy(endMinutes = segment.endMinutes)
            else merged.add(segment)
        }
        val certain = merged.filter { !it.tentative }
        val possible = merged.filter { it.tentative }
        val lines = mutableListOf<String>()
        if (certain.isNotEmpty()) lines += certain.joinToString("  ·  ") { "${clock(it.startMinutes)}–${clock(it.endMinutes)}" }
        if (possible.isNotEmpty()) lines += "Можливо: " + possible.joinToString("  ·  ") { "${clock(it.startMinutes)}–${clock(it.endMinutes)}" }
        if (lines.isEmpty()) lines += "За опублікованим графіком відключень немає"
        val update = fact.optString("update", "час невідомий")
        lines += "Графік оновлено: $update"
        return Result(lines.joinToString("\n"), merged, update)
    }
}
''', encoding='utf-8')
print('OukitelMonitor 2.5: outage schedule below battery; address and queue settings; manual refresh')
