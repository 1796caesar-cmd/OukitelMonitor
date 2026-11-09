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


# 2.6: two explicit modes and a dedicated settings submenu.  The existing
# GitHub Actions workflow already executes THIS script, so replacing only this
# file is enough for one commit -> one signed APK -> one release.
main = MAIN.read_text(encoding='utf-8')
gradle = GRADLE.read_text(encoding='utf-8')

main = one(main,
'''        addOutageSettings(root)
        gap(root,26)
''',
'''        settingsItem(root, "⚡  Графік відключень", "Показувати сьогодні · за чергою або за адресою") {
            showOutageSettingsPage()
        }
        gap(root,26)
''', 'replace settings inline form with submenu')

# Drop the old combined form. Preserve the dashboard card, its refresh button
# and its schedule-fetch/cache implementation unmodified.
old_start = '    // The selected address is only an on-device label.'
old_end = '    private fun showOutagePanel(root: LinearLayout) {'
if main.count(old_start) != 1 or main.count(old_end) != 1:
    raise RuntimeError('Could not locate 2.5 form for 2.6 replacement')
a = main.index(old_start)
b = main.index(old_end, a)

submenu_and_lookup = r'''    /** Settings are isolated from the home screen so they stay easy to navigate. */
    private fun showOutageSettingsPage() {
        currentScreen = "outage_settings"
        active = false
        handler.removeCallbacks(tick)
        val p = prefs()
        val root = column().apply {
            background = forestBackground()
            setPadding(dp(18), dp(22), dp(18), dp(24))
        }
        val back = text("‹   Налаштування", 18f, green, true).apply {
            setPadding(0, dp(8), 0, dp(8))
            setOnClickListener { showSettings() }
        }
        add(root, back); gap(root, 18)
        add(root, text("Графік відключень", 26f, white, true)); gap(root, 14)
        val toggleRow = row().apply {
            gravity = Gravity.CENTER_VERTICAL
            background = shape(panel, 18, green)
            setPadding(dp(12), dp(10), dp(9), dp(10))
        }
        toggleRow.addView(text("Відображати на головному екрані", 15f, white, true),
            LinearLayout.LayoutParams(0, -2, 1f))
        val enabled = Switch(this).apply { isChecked = p.getBoolean("show_outage_schedule", false) }
        toggleRow.addView(enabled)
        add(root, toggleRow); gap(root, 20)

        add(root, text("Спосіб вибору графіка", 18f, white, true)); gap(root, 8)
        val options = RadioGroup(this).apply {
            orientation = RadioGroup.VERTICAL
            background = shape(panel, 18, green)
            setPadding(dp(12), dp(8), dp(12), dp(8))
        }
        val byQueue = RadioButton(this).apply {
            id = View.generateViewId()
            text = "За чергою"
            setTextColor(white)
            textSize = 16f
        }
        val byAddress = RadioButton(this).apply {
            id = View.generateViewId()
            text = "За адресою"
            setTextColor(white)
            textSize = 16f
        }
        options.addView(byQueue); options.addView(byAddress)
        options.check(if (p.getString("outage_mode", "queue") == "address") byAddress.id else byQueue.id)
        add(root, options); gap(root, 15)

        val queueBox = column()
        add(queueBox, text("Підчерга", 16f, white, true)); gap(queueBox, 8)
        val queues = arrayOf("Оберіть підчергу", "1.1", "1.2", "2.1", "2.2", "3.1", "3.2",
            "4.1", "4.2", "5.1", "5.2", "6.1", "6.2")
        val spinner = Spinner(this)
        spinner.adapter = object : ArrayAdapter<String>(this,
            android.R.layout.simple_spinner_dropdown_item, queues) {
            override fun getView(position: Int, convertView: View?, parent: android.view.ViewGroup): View =
                super.getView(position, convertView, parent).also {
                    (it as? TextView)?.setTextColor(white)
                    it.setPadding(dp(12), dp(10), dp(12), dp(10))
                }
            override fun getDropDownView(position: Int, convertView: View?, parent: android.view.ViewGroup): View =
                super.getDropDownView(position, convertView, parent).also {
                    (it as? TextView)?.setTextColor(Color.rgb(30, 43, 50))
                }
        }
        spinner.background = shape(palette.tile, 16, green)
        val savedQueue = p.getString("outage_queue_choice", p.getString("outage_group", "")) ?: ""
        spinner.setSelection(queues.indexOf(savedQueue).coerceAtLeast(0))
        add(queueBox, spinner); gap(queueBox, 8)
        add(queueBox, text("Вибери підчергу для свого будинку (1.1–6.2).", 13f, muted))
        add(root, queueBox)

        val addressBox = column()
        val addr = p.getString("outage_selected_address", "").orEmpty()
        val addrGroup = p.getString("outage_selected_group", "").orEmpty()
        val description = text(
            if (addr.isNotBlank() && OutageSchedule.VALID_GROUPS.contains(addrGroup))
                "$addr  ·  підчерга $addrGroup"
            else "Адресу ще не вибрано", 15f, white)
        add(addressBox, description); gap(addressBox, 12)
        val search = text("⌕   Вибрати адресу зі списку", 16f, green, true).apply {
            background = shape(panel, 17, green)
            gravity = Gravity.CENTER
            setPadding(dp(14), dp(16), dp(14), dp(16))
            setOnClickListener { showOfficialAddressSearch() }
        }
        add(addressBox, search); gap(addressBox, 10)
        add(addressBox, text(
            "Пошук відкриває сайт Житомиробленерго в додатку. " +
            "Там обери РЕМ, населений пункт і вулицю, потім натисни «Вибрати адресу». " +
            "Підчерга буде взята з обраного офіційного запису.", 12f, muted))
        add(root, addressBox); gap(root, 18)

        fun switchMode() {
            queueBox.visibility = if (byQueue.isChecked) View.VISIBLE else View.GONE
            addressBox.visibility = if (byAddress.isChecked) View.VISIBLE else View.GONE
        }
        options.setOnCheckedChangeListener { _, _ -> switchMode() }
        switchMode()

        val save = text("✓   Зберегти", 17f, white, true).apply {
            gravity = Gravity.CENTER
            background = shape(palette.tile, 17, green)
            setPadding(dp(15), dp(15), dp(15), dp(15))
        }
        add(root, save); gap(root, 16)
        save.setOnClickListener {
            val mode = if (byAddress.isChecked) "address" else "queue"
            val selectedQueue = if (mode == "queue") {
                queues[spinner.selectedItemPosition].takeIf { spinner.selectedItemPosition > 0 }.orEmpty()
            } else p.getString("outage_selected_group", "").orEmpty()
            val selectedAddr = if (mode == "address") p.getString("outage_selected_address", "").orEmpty() else ""
            if (enabled.isChecked && (selectedQueue !in OutageSchedule.VALID_GROUPS ||
                        (mode == "address" && selectedAddr.isBlank()))) {
                Toast.makeText(this, if (mode == "address") "Спочатку вибери адресу зі списку"
                    else "Спочатку вибери підчергу", Toast.LENGTH_LONG).show()
                return@setOnClickListener
            }
            val previous = p.getString("outage_group", "").orEmpty()
            p.edit().putBoolean("show_outage_schedule", enabled.isChecked)
                .putString("outage_mode", mode)
                .putString("outage_group", selectedQueue)
                .putString("outage_address", selectedAddr)
                .putString("outage_queue_choice", if (mode == "queue") selectedQueue else savedQueue)
                .apply()
            if (previous != selectedQueue) p.edit().remove("outage_cache_json")
                .remove("outage_cache_group").remove("outage_cache_fetched").apply()
            Toast.makeText(this, "Налаштування збережено", Toast.LENGTH_SHORT).show()
            showSettings()
        }
        setContentView(ScrollView(this).apply {
            background = forestBackground()
            isFillViewport = true
            addView(root)
        })
    }

    /** The official search is embedded, not an undocumented Svitlochek API. */
    private fun showOfficialAddressSearch() {
        currentScreen = "outage_address"
        active = false
        handler.removeCallbacks(tick)
        val root = column().apply {
            background = forestBackground()
            setPadding(dp(10), dp(13), dp(10), dp(15))
        }
        val back = text("‹   Графік відключень", 17f, green, true).apply {
            setPadding(dp(8), dp(6), dp(8), dp(8))
            setOnClickListener { showOutageSettingsPage() }
        }
        add(root, back); gap(root, 8)
        val hint = text("На сайті вибери РЕМ, населений пункт і вулицю.", 13f, white)
        add(root, hint); gap(root, 8)
        val web = android.webkit.WebView(this).apply {
            settings.javaScriptEnabled = true // Required by the official address selectors.
            settings.domStorageEnabled = true
            settings.useWideViewPort = true
            settings.loadWithOverviewMode = true
            settings.builtInZoomControls = true
            settings.displayZoomControls = false
            webViewClient = object : android.webkit.WebViewClient() {
                override fun shouldOverrideUrlLoading(view: android.webkit.WebView,
                    request: android.webkit.WebResourceRequest): Boolean {
                    val uri = request.url
                    val host = uri.host.orEmpty().lowercase(Locale.ROOT)
                    return uri.scheme != "https" || (host != "ztoe.com.ua" && host != "www.ztoe.com.ua")
                }
                override fun onPageFinished(view: android.webkit.WebView, url: String) {
                    hint.text = "Знайди свою вулицю на сайті, тоді натисни кнопку під сторінкою."
                }
            }
        }
        root.addView(web, LinearLayout.LayoutParams(-1, 0, 1f))
        web.loadUrl("https://www.ztoe.com.ua/unhooking-search.php")
        gap(root, 10)
        val pick = text("✓   Вибрати адресу з результатів", 15f, white, true).apply {
            gravity = Gravity.CENTER
            background = shape(palette.tile, 17, green)
            setPadding(dp(12), dp(13), dp(12), dp(13))
        }
        add(root, pick)
        pick.setOnClickListener {
            // Read only published result rows. Do not submit addresses to any
            // unofficial server, guess a queue or scrape unrelated websites.
            val js = """(function(){
                try {
                    var rows = [], tr = document.querySelectorAll('tr');
                    for (var i = 0; i < tr.length; i++) {
                        var td = tr[i].querySelectorAll('td');
                        if (td.length < 7) continue;
                        var x = [];
                        for(var j = 0; j < td.length; j++) {
                            x.push((td[j].innerText || td[j].textContent || '').replace(/\s+/g,' ').trim());
                        }
                        if (!/^[1-6]$/.test(x[4]) || !/^[12]$/.test(x[5])) continue;
                        if (!x[1] || !x[2] || !x[3]) continue;
                        rows.push({city:x[1], street:x[2], houses:x[3],
                            group:x[4]+'.'+x[5], note:x[6] || ''});
                    }
                    return JSON.stringify({total:rows.length, rows:rows.slice(0,100)});
                } catch(e) { return JSON.stringify({error:String(e)}); }
            })()""".trimIndent()
            web.evaluateJavascript(js) { encoded ->
                if (currentScreen != "outage_address") return@evaluateJavascript
                try {
                    val decoded = org.json.JSONTokener(encoded).nextValue().toString()
                    val response = JSONObject(decoded)
                    val total = response.optInt("total", 0)
                    if (response.has("error")) throw IllegalArgumentException(response.optString("error"))
                    if (total == 0) {
                        android.app.AlertDialog.Builder(this)
                            .setTitle("Адрес не знайдено")
                            .setMessage("Спочатку вибери РЕМ, населений пункт і вулицю на сайті. " +
                                "Якщо офіційний сайт змінив структуру, спробуй режим «За чергою».")
                            .setPositiveButton("Зрозуміло", null).show()
                        return@evaluateJavascript
                    }
                    if (total > 100) {
                        android.app.AlertDialog.Builder(this)
                            .setTitle("Забагато адрес")
                            .setMessage("Знайдено $total записів. Уточни населений пункт або вулицю на сайті.")
                            .setPositiveButton("Зрозуміло", null).show()
                        return@evaluateJavascript
                    }
                    val array = response.getJSONArray("rows")
                    val list = mutableListOf<JSONObject>()
                    val labels = mutableListOf<String>()
                    for (i in 0 until array.length()) {
                        val row = array.optJSONObject(i) ?: continue
                        val group = row.optString("group")
                        if (group !in OutageSchedule.VALID_GROUPS) continue
                        list.add(row)
                        labels.add("${row.optString("city")}, ${row.optString("street")} · " +
                            "${row.optString("houses")} · черга $group" +
                            (if (row.optString("note").isNotBlank()) " · ${row.optString("note")}" else ""))
                    }
                    if (list.isEmpty()) throw IllegalStateException("Немає коректних записів з підчергами")
                    android.app.AlertDialog.Builder(this)
                        .setTitle("Вибери свою адресу")
                        .setItems(labels.toTypedArray()) { _, index ->
                            val row = list[index]
                            val town = row.optString("city")
                            val street = row.optString("street")
                            val group = row.optString("group")
                            val houses = row.optString("houses")
                                .split(Regex("[,;]"))
                                .map { it.trim() }.filter { it.isNotBlank() }
                            if (houses.size > 1 && houses.size <= 120) {
                                android.app.AlertDialog.Builder(this)
                                    .setTitle("Номер будинку · $street")
                                    .setItems(houses.toTypedArray()) { _, n ->
                                        saveSelectedOutageAddress("$town, $street, ${houses[n]}", group)
                                    }.setNegativeButton("Скасувати", null).show()
                            } else if (houses.isNotEmpty()) {
                                saveSelectedOutageAddress("$town, $street, ${houses.joinToString(", ")}", group)
                            } else {
                                Toast.makeText(this, "У записі немає номера будинку", Toast.LENGTH_LONG).show()
                            }
                        }.setNegativeButton("Скасувати", null).show()
                } catch (e: Exception) {
                    android.app.AlertDialog.Builder(this)
                        .setTitle("Не вдалося прочитати адресу")
                        .setMessage(e.message ?: "Помилка розпізнавання сторінки")
                        .setPositiveButton("Зрозуміло", null).show()
                }
            }
        }
        setContentView(root)
    }

    private fun saveSelectedOutageAddress(address: String, queue: String) {
        if (queue !in OutageSchedule.VALID_GROUPS || address.isBlank()) return
        val p = prefs()
        val previous = p.getString("outage_group", "")
        p.edit().putString("outage_selected_address", address)
            .putString("outage_selected_group", queue)
            .putString("outage_mode", "address")
            .putString("outage_group", queue)
            .putString("outage_address", address)
            .putBoolean("show_outage_schedule", true)
            .apply()
        if (previous != queue) p.edit().remove("outage_cache_json")
            .remove("outage_cache_group").remove("outage_cache_fetched").apply()
        Toast.makeText(this, "Адресу збережено · підчерга $queue", Toast.LENGTH_SHORT).show()
        showOutageSettingsPage()
    }

'''
main = main[:a] + submenu_and_lookup + main[b:]

# Android back button follows the new submenu hierarchy.
old_back = '''        if (currentScreen == "settings" || currentScreen == "alerts" || currentScreen == "statistics") {
            showDashboard(session?.name ?: "P1000E Plus")
            loadData()
        } else {
            super.onBackPressed()
        }'''
new_back = '''        when (currentScreen) {
            "outage_address" -> showOutageSettingsPage()
            "outage_settings" -> showSettings()
            "settings", "alerts", "statistics" -> {
                showDashboard(session?.name ?: "P1000E Plus")
                loadData()
            }
            else -> super.onBackPressed()
        }'''
main = one(main, old_back, new_back, 'Android back navigation for nested outage settings')

gradle = one(gradle, 'versionName = "2.5"', 'versionName = "2.6"', 'bump to 2.6')
MAIN.write_text(main, encoding='utf-8')
GRADLE.write_text(gradle, encoding='utf-8')
print('OukitelMonitor 2.6: nested outage settings with queue or official address browser')

# 2.7 — experimental telemetry retrieval + detailed in-app APK download progress.
# This is deliberately appended to the EXISTING 2.5/2.6 update script so the
# existing one-Android-workflow GitHub Actions configuration remains unchanged.
# Run AFTER the previous patch sections: versionName should be 2.6 here.
from pathlib import Path as _Path27

_service27_path = ROOT / 'app/src/main/java/com/oukitel/monitor/MonitorService.kt'
_updater27_path = ROOT / 'app/src/main/java/com/oukitel/monitor/UpdateManager.kt'

_main27 = MAIN.read_text(encoding='utf-8')
_service27 = _service27_path.read_text(encoding='utf-8')
_updater27 = _updater27_path.read_text(encoding='utf-8')
_gradle27 = GRADLE.read_text(encoding='utf-8')

# OFF by default. When turned OFF, neither the UI nor the background Service
# sends batchControlDevice(high_frequency_reporting=3). Existing GET telemetry
# requests, authentication, alerts and polling intervals remain untouched.
_main27 = one(_main27,
    '    private fun wakeCloud(s: Session) {\n',
    '''    private fun wakeCloud(s: Session) {
        if (!prefs().getBoolean("active_data_reporting_enabled", false)) return
''', '2.7: disable high-frequency command in Activity by default')
_service27 = one(_service27,
    '    private fun wakeCloud(session: JSONObject) {\n',
    '''    private fun wakeCloud(session: JSONObject) {
        if (!prefs.getBoolean("active_data_reporting_enabled", false)) return
''', '2.7: disable high-frequency command in background Service by default')

# Track *successful, structurally valid background reads*, not attempted polls.
# It is NOT the station's own timestamp (Wonderfree may return cached data).
_service27 = one(_service27,
    '''                val output = values[5]
                StatisticsStore.record(this, battery, input, output)''',
    '''                val output = values[5]
                if (battery != null && input != null && output != null) {
                    prefs.edit().putLong("background_last_valid_read_ms", System.currentTimeMillis()).apply()
                }
                StatisticsStore.record(this, battery, input, output)''',
    '2.7: record a successful background snapshot')

# Keep the main Settings screen uncluttered: a small radio group below background
# controls, with immediate persistence; no app restart and no extra service.
_retrieval27 = r'''    private fun addDataRetrievalSettings(root: LinearLayout) {
        val p = prefs()
        add(root, text("Отримання даних станції", 19f, white, true)); gap(root, 9)
        add(root, text("Експериментальний режим · впливає і на екран додатка, і на фонове оновлення.", 13f, muted))
        gap(root, 10)
        val choice = RadioGroup(this).apply {
            orientation = RadioGroup.VERTICAL
            background = shape(panel, 18, green)
            setPadding(dp(12), dp(8), dp(12), dp(8))
        }
        val normal = RadioButton(this).apply {
            id = View.generateViewId()
            text = "Звичайний — без примусової активації"
            setTextColor(white)
            textSize = 15f
        }
        val activeMode = RadioButton(this).apply {
            id = View.generateViewId()
            text = "Активний — як у попередніх версіях"
            setTextColor(white)
            textSize = 15f
        }
        choice.addView(normal)
        choice.addView(activeMode)
        choice.check(if (p.getBoolean("active_data_reporting_enabled", false)) activeMode.id else normal.id)
        choice.setOnCheckedChangeListener { _, checkedId ->
            val newActive = checkedId == activeMode.id
            p.edit().putBoolean("active_data_reporting_enabled", newActive).apply()
            Toast.makeText(this,
                if (newActive) "Активне передавання увімкнено" else "Звичайне отримання даних увімкнено",
                Toast.LENGTH_SHORT).show()
        }
        add(root, choice); gap(root, 8)
        add(root, text("Звичайний режим лише читає показники Wonderfree. Активний додатково надсилає команду високочастотного передавання, яка може будити дисплей станції.", 12f, muted))
        gap(root, 9)
        val lastRead = p.getLong("background_last_valid_read_ms", 0L)
        val lastTime = if (lastRead > 0L)
            SimpleDateFormat("dd.MM.yyyy HH:mm", Locale("uk", "UA")).format(Date(lastRead))
            else "ще немає"
        add(root, text("Остання успішна фонова відповідь: $lastTime", 12f, green))
        add(root, text("Час відповіді Wonderfree не гарантує, що дані станції свіжі.", 12f, muted))
    }

'''
_main27 = one(_main27,
    '    private fun showSettings() {',
    _retrieval27 + '    private fun showSettings() {',
    '2.7: data retrieval settings UI')
_main27 = one(_main27,
    '''        addBackgroundSettings(root)
        gap(root,26)''',
    '''        addBackgroundSettings(root)
        gap(root,26)
        addDataRetrievalSettings(root)
        gap(root,26)''',
    '2.7: insert retrieval options above outage settings')

# The updater already had a horizontal bar, but it only jumped by 5 percent.
# Use a visible percentage plus downloaded/total megabytes and report 1%
# steps, with a time-throttled update when the integer percentage is unchanged.
_old_progress27 = '''        val progress = ProgressBar(activity, null, android.R.attr.progressBarStyleHorizontal)
        progress.max = 100
        progress.progress = 0
        val label = TextView(activity).apply {
            text = "Завантаження: 0%"
            setPadding(28, 18, 28, 16)
        }
        val content = android.widget.LinearLayout(activity).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setPadding(45, 25, 45, 25)
            addView(label)
            addView(progress)
        }
        val dialog = AlertDialog.Builder(activity).setTitle("Оновлення Oukitel Monitor")
            .setView(content).setCancelable(false).create()
        dialog.show()'''
_new_progress27 = '''        val progress = ProgressBar(activity, null, android.R.attr.progressBarStyleHorizontal)
        progress.max = 100
        progress.progress = 0
        val mbTotal = release.size / 1_000_000.0
        val label = TextView(activity).apply {
            text = "0%"
            textSize = 26f
            gravity = android.view.Gravity.CENTER
            setPadding(0, 8, 0, 4)
        }
        val sizeLabel = TextView(activity).apply {
            text = String.format(Locale("uk", "UA"), "%.2f / %.2f МБ", 0.0, mbTotal)
            textSize = 15f
            gravity = android.view.Gravity.CENTER
            setPadding(0, 0, 0, 14)
        }
        val content = android.widget.LinearLayout(activity).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            val inset = (20 * resourcesDisplayDensity(activity)).toInt()
            setPadding(inset, inset, inset, inset)
            addView(label)
            addView(sizeLabel)
            addView(progress)
        }
        val dialog = AlertDialog.Builder(activity).setTitle("Завантаження Oukitel Monitor ${release.version}")
            .setView(content).setCancelable(false).create()
        dialog.show()'''
# No dependency on Activity.resources in the object: use a simple pure helper.
_updater27 = one(_updater27,
    '    private fun downloadAndInstall(activity: Activity, release: Release) {',
    '''    private fun resourcesDisplayDensity(activity: Activity): Float = activity.resources.displayMetrics.density

    private fun downloadAndInstall(activity: Activity, release: Release) {''',
    '2.7: dialog padding helper')
_updater27 = one(_updater27, _old_progress27, _new_progress27,
    '2.7: download dialog with MB progress')
_updater27 = one(_updater27,
    '''                    var total = 0L
                    var shown = -1''',
    '''                    var total = 0L
                    var shown = -1
                    var lastUiTime = 0L''',
    '2.7: update progress throttling')
_updater27 = one(_updater27,
    '''                                if (pct != shown && pct % 5 == 0) {
                                    shown = pct
                                    activity.runOnUiThread {
                                        progress.progress = pct
                                        label.text = "Завантаження: $pct%"
                                    }
                                }''',
    '''                                val nowMs = System.currentTimeMillis()
                                if (pct != shown || nowMs - lastUiTime >= 300L || total == release.size) {
                                    shown = pct
                                    lastUiTime = nowMs
                                    val downloadedMb = total / 1_000_000.0
                                    activity.runOnUiThread {
                                        progress.progress = pct
                                        label.text = "$pct%"
                                        sizeLabel.text = String.format(Locale("uk", "UA"),
                                            "%.2f / %.2f МБ", downloadedMb, mbTotal)
                                    }
                                }''',
    '2.7: MB and percent in each update')
_updater27 = one(_updater27,
    '''                    if (total != release.size) throw IllegalStateException("APK завантажився не повністю")''',
    '''                    if (total != release.size) throw IllegalStateException("APK завантажився не повністю")
                    activity.runOnUiThread {
                        progress.progress = 100
                        label.text = "100%"
                        sizeLabel.text = String.format(Locale("uk", "UA"),
                            "%.2f / %.2f МБ · Перевірка файлу…", mbTotal, mbTotal)
                    }''',
    '2.7: APK verification state')

_gradle27 = one(_gradle27, 'versionName = "2.6"', 'versionName = "2.7"', 'Android 2.7 versionName')

# Changes are written only after every required anchor was found once.
MAIN.write_text(_main27, encoding='utf-8')
_service27_path.write_text(_service27, encoding='utf-8')
_updater27_path.write_text(_updater27, encoding='utf-8')
GRADLE.write_text(_gradle27, encoding='utf-8')
print('OukitelMonitor 2.7: optional high-frequency command + detailed download dialog (MB, %, bar)')


# 2.8 — five-minute battery history, native cascading address picker and
# restore known-working active reporting on the first launch after upgrading.
# This is part of the existing one-file patch: one commit triggers one Android
# build and one release, without another Actions YAML workflow.
_stats28_path = ROOT / 'app/src/main/java/com/oukitel/monitor/Statistics.kt'
_main28 = MAIN.read_text(encoding='utf-8')
_stats28 = _stats28_path.read_text(encoding='utf-8')
_gradle28 = GRADLE.read_text(encoding='utf-8')

# Restore old battery history and retain all REAL samples up to every five
# minutes. SQLite avoids serializing a growing 31-day JSON list on each read.
_stats_begin28 = 'object StatisticsStore {'
_stats_end28 = 'class StatisticsChart('
if _stats28.count(_stats_begin28) != 1 or _stats28.count(_stats_end28) != 1:
    raise RuntimeError('2.8: StatisticsStore/StatisticsChart boundaries not found')
_sa28 = _stats28.index(_stats_begin28)
_sb28 = _stats28.index(_stats_end28, _sa28)
_stats28 = _stats28[:_sa28] + '/** Battery history from successful reads: no more than one sample per five\n * minutes. The old 31-day JSON history is imported into SQLite once. */\nobject StatisticsStore {\n    data class Sample(val timestamp: Long, val battery: Int?, val input: Double?, val output: Double?)\n\n    private class HistoryDb(context: Context) :\n        android.database.sqlite.SQLiteOpenHelper(context, "oukitel_telemetry.db", null, 1) {\n        override fun onCreate(db: android.database.sqlite.SQLiteDatabase) {\n            db.execSQL("CREATE TABLE IF NOT EXISTS samples (id INTEGER PRIMARY KEY AUTOINCREMENT, t INTEGER NOT NULL, b INTEGER, i REAL, o REAL)")\n            db.execSQL("CREATE INDEX IF NOT EXISTS samples_time ON samples(t)")\n        }\n        override fun onUpgrade(db: android.database.sqlite.SQLiteDatabase, oldVersion: Int, newVersion: Int) {\n            // Schema v1 does not have an upgrade yet; do not discard history.\n        }\n    }\n\n    private var helper: HistoryDb? = null\n    private fun db(context: Context): android.database.sqlite.SQLiteDatabase {\n        if (helper == null) helper = HistoryDb(context.applicationContext)\n        return helper!!.writableDatabase\n    }\n\n    /** Import pre-2.8 graph points once, without rewriting or inventing values. */\n    private fun migrate(context: Context, sql: android.database.sqlite.SQLiteDatabase) {\n        val prefs = context.getSharedPreferences("oukitel", Context.MODE_PRIVATE)\n        if (prefs.getBoolean("statistics_sqlite_migrated_v1", false)) return\n        val old = prefs.getString("statistics", "[]") ?: "[]"\n        val items = try { JSONArray(old) } catch (_: Exception) { JSONArray() }\n        sql.beginTransaction()\n        try {\n            for (index in 0 until items.length()) {\n                val x = items.optJSONObject(index) ?: continue\n                val t = x.optLong("t", 0L)\n                if (t <= 0L) continue\n                val values = android.content.ContentValues().apply {\n                    put("t", t)\n                    if (x.has("b") && !x.isNull("b")) put("b", x.optInt("b"))\n                    if (x.has("i") && !x.isNull("i")) put("i", x.optDouble("i"))\n                    if (x.has("o") && !x.isNull("o")) put("o", x.optDouble("o"))\n                }\n                sql.insertOrThrow("samples", null, values)\n            }\n            sql.setTransactionSuccessful()\n        } finally { sql.endTransaction() }\n        prefs.edit().putBoolean("statistics_sqlite_migrated_v1", true)\n            .remove("statistics").remove("statistics_last").apply()\n    }\n\n    @Synchronized fun record(context: Context, battery: Int?, input: Double?, output: Double?) {\n        if (battery == null && input == null && output == null) return\n        try {\n            val sql = db(context)\n            migrate(context, sql)\n            val now = System.currentTimeMillis()\n            // The foreground UI and background service share this synchronized\n            // method, so concurrent updates still obey the five-minute limit.\n            val lastSample = sql.rawQuery("SELECT t FROM samples ORDER BY t DESC LIMIT 1", null).use {\n                if (it.moveToFirst()) it.getLong(0) else 0L\n            }\n            if (lastSample > 0L && now - lastSample < 300_000L) return\n            val item = android.content.ContentValues().apply {\n                put("t", now)\n                if (battery != null) put("b", battery.coerceIn(0, 100))\n                if (input != null && input.isFinite()) put("i", input)\n                if (output != null && output.isFinite()) put("o", output)\n            }\n            sql.insertOrThrow("samples", null, item)\n            val prefs = context.getSharedPreferences("oukitel", Context.MODE_PRIVATE)\n            val previousPrune = prefs.getLong("statistics_sqlite_last_prune", 0L)\n            if (now - previousPrune > 60L * 60L * 1000L) {\n                sql.delete("samples", "t < ?", arrayOf((now - 31L * 24 * 60 * 60 * 1000L).toString()))\n                prefs.edit().putLong("statistics_sqlite_last_prune", now).apply()\n            }\n        } catch (_: Exception) {\n            // Telemetry alerts must not fail if local history storage is full.\n        }\n    }\n\n    @Synchronized fun read(context: Context, hours: Int): List<Sample> {\n        val result = ArrayList<Sample>()\n        try {\n            val sql = db(context)\n            migrate(context, sql)\n            val since = System.currentTimeMillis() - hours.toLong() * 3_600_000L\n            val cursor = sql.rawQuery(\n                "SELECT t,b,i,o FROM samples WHERE t>=? ORDER BY t ASC,id ASC",\n                arrayOf(since.toString()))\n            cursor.use {\n                while (it.moveToNext()) {\n                    result.add(Sample(it.getLong(0),\n                        if (it.isNull(1)) null else it.getInt(1),\n                        if (it.isNull(2)) null else it.getDouble(2),\n                        if (it.isNull(3)) null else it.getDouble(3)))\n                }\n            }\n        } catch (_: Exception) {\n            // If storage is unavailable the chart stays empty, never guessed.\n        }\n        return result\n    }\n}\n\n' + _stats28[_sb28:]

# The former page-sized browser gets replaced with four native Android
# selectors, fed from the operator's live, hidden official webpage DOM.
_begin28 = '    private fun showOfficialAddressSearch() {'
_end28 = '    private fun saveSelectedOutageAddress(address: String, queue: String) {'
if _main28.count(_begin28) != 1 or _main28.count(_end28) != 1:
    raise RuntimeError('2.8: official address browser anchors not found')
_a28 = _main28.index(_begin28)
_b28 = _main28.index(_end28, _a28)
_main28 = _main28[:_a28] + '    /** Native address picker. The official page runs invisibly as a read-only\n     * source for REM, town, street and house options. We do not ship a made-up\n     * address directory or call private/unverified Svitlochek endpoints. */\n    private fun showOfficialAddressSearch() {\n        currentAddressLookup?.close()\n        val picker = OutageAddressLookup()\n        currentAddressLookup = picker\n        picker.show()\n    }\n\n    private data class OutageChoice(val index: Int, val label: String)\n    private data class OutageHome(val number: String, val queue: String, val note: String)\n\n    private inner class OutageAddressLookup {\n        private val sourceUrl = "https://www.ztoe.com.ua/unhooking-search.php"\n        private val browser = android.webkit.WebView(this@MainActivity)\n        private val status = text("Підключення до Житомиробленерго…", 13f, muted)\n        private val remButton = chooser("1. РЕМ: завантаження…")\n        private val townButton = chooser("2. Населений пункт: обрати РЕМ")\n        private val streetButton = chooser("3. Вулиця: обрати населений пункт")\n        private val houseButton = chooser("4. Будинок: обрати вулицю")\n        private var closed = false\n        private var loaded = false\n        private var generation = 0\n        private var remName = ""\n        private var townName = ""\n        private var streetName = ""\n        private var homes = emptyList<OutageHome>()\n\n        private fun chooser(title: String) = text(title, 16f, white, true).apply {\n            background = shape(panel, 17, green)\n            setPadding(dp(15), dp(17), dp(15), dp(17))\n            isEnabled = false\n            alpha = 0.65f\n        }\n\n        private fun enable(view: TextView, enabled: Boolean) {\n            view.isEnabled = enabled\n            view.alpha = if (enabled) 1f else 0.65f\n        }\n\n        fun close() {\n            if (closed) return\n            closed = true\n            generation++\n            try {\n                browser.stopLoading()\n                browser.destroy()\n            } catch (_: Exception) { }\n        }\n\n        private fun warning(message: String) {\n            if (closed || currentScreen != "outage_address") return\n            status.text = message\n            status.setTextColor(Color.rgb(255, 179, 76))\n        }\n\n        fun show() {\n            currentScreen = "outage_address"\n            active = false\n            handler.removeCallbacks(tick)\n            val root = column().apply {\n                background = forestBackground()\n                setPadding(dp(17), dp(24), dp(17), dp(25))\n            }\n            add(root, text("‹   Графік відключень", 17f, green, true).apply {\n                setPadding(dp(3), dp(8), dp(3), dp(8))\n                setOnClickListener { showOutageSettingsPage() }\n            }); gap(root, 18)\n            add(root, text("Вибір адреси", 25f, white, true)); gap(root, 9)\n            add(root, text("Обери адресу зі списків Житомиробленерго. Сайт відкривати не потрібно.", 13f, muted))\n            gap(root, 16)\n            add(root, remButton); gap(root, 10)\n            add(root, townButton); gap(root, 10)\n            add(root, streetButton); gap(root, 10)\n            add(root, houseButton); gap(root, 14)\n            add(root, status)\n            gap(root, 8)\n            add(root, text("Якщо довідник недоступний, можна обрати підчергу вручну в попередньому меню.", 12f, muted))\n            // Attached to the Activity, but hidden: only its published DOM is\n            // read. The user sees the four native Android selectors above.\n            browser.alpha = 0f\n            browser.isFocusable = false\n            browser.settings.javaScriptEnabled = true\n            browser.settings.domStorageEnabled = true\n            browser.settings.allowFileAccess = false\n            browser.settings.allowContentAccess = false\n            browser.webViewClient = object : android.webkit.WebViewClient() {\n                override fun shouldOverrideUrlLoading(\n                    view: android.webkit.WebView,\n                    request: android.webkit.WebResourceRequest\n                ): Boolean {\n                    val uri = request.url\n                    val host = uri.host.orEmpty().lowercase(Locale.ROOT)\n                    return uri.scheme != "https" || (host != "ztoe.com.ua" && host != "www.ztoe.com.ua")\n                }\n                override fun onPageFinished(view: android.webkit.WebView, url: String) {\n                    if (closed || currentScreen != "outage_address" || !url.startsWith("https://")) return\n                    loaded = true\n                    if (remName.isBlank()) checkOptions(0, 0)\n                    else if (townName.isBlank()) checkOptions(1, 0)\n                    else if (streetName.isBlank()) checkOptions(2, 0)\n                    else checkHouses(0)\n                }\n                override fun onReceivedError(view: android.webkit.WebView,\n                    request: android.webkit.WebResourceRequest,\n                    error: android.webkit.WebResourceError) {\n                    if (request.isForMainFrame) warning("Не вдалося завантажити довідник адрес. Перевір інтернет.")\n                }\n            }\n            root.addView(browser, LinearLayout.LayoutParams(dp(1), dp(1)))\n            remButton.setOnClickListener { showOptions(0) }\n            townButton.setOnClickListener { showOptions(1) }\n            streetButton.setOnClickListener { showOptions(2) }\n            houseButton.setOnClickListener { showHouses() }\n            setContentView(ScrollView(this@MainActivity).apply {\n                background = forestBackground()\n                isFillViewport = true\n                addView(root)\n            })\n            browser.loadUrl(sourceUrl)\n        }\n\n        private fun evaluate(js: String, callback: (JSONObject) -> Unit) {\n            if (closed || !loaded || currentScreen != "outage_address") return\n            browser.evaluateJavascript(js) { raw ->\n                if (closed || currentScreen != "outage_address") return@evaluateJavascript\n                try {\n                    // evaluateJavascript returns a JSON-encoded JavaScript string.\n                    val decoded = org.json.JSONTokener(raw).nextValue().toString()\n                    callback(JSONObject(decoded))\n                } catch (_: Exception) {\n                    warning("Не вдалося прочитати дані сайту. Можна вибрати графік за чергою.")\n                }\n            }\n        }\n\n        private fun optionsScript(step: Int) = """(function(){\n            try {\n                var el = document.querySelectorAll(\'select\')[$step];\n                if (!el) return JSON.stringify({items:[], error:\'Відсутній список\'});\n                var a = [];\n                for (var i = 0; i < el.options.length; i++) {\n                    var o = el.options[i], name = (o.textContent || \'\').replace(/\\s+/g,\' \').trim();\n                    if (o.disabled || !o.value || !name || /^-+$/.test(name) ||\n                        /^(-?\\s*(оберіть|виберіть|select|вкажіть))/i.test(name)) continue;\n                    a.push({index:i,label:name});\n                }\n                return JSON.stringify({items:a});\n            } catch(e){return JSON.stringify({items:[],error:String(e)});}\n        })()""".trimIndent()\n\n        private fun choices(obj: JSONObject): List<OutageChoice> {\n            val list = obj.optJSONArray("items") ?: return emptyList()\n            val choices = mutableListOf<OutageChoice>()\n            for (i in 0 until list.length()) {\n                val o = list.optJSONObject(i) ?: continue\n                val index = o.optInt("index", -1)\n                val name = o.optString("label").trim()\n                if (index >= 0 && name.isNotBlank()) choices.add(OutageChoice(index, name))\n            }\n            return choices\n        }\n\n        private fun checkOptions(step: Int, attempt: Int) {\n            if (closed || currentScreen != "outage_address") return\n            val token = generation\n            handler.postDelayed({\n                if (closed || token != generation || currentScreen != "outage_address") return@postDelayed\n                evaluate(optionsScript(step)) { result ->\n                    val items = choices(result)\n                    if (items.isNotEmpty()) {\n                        when (step) {\n                            0 -> { remButton.text = "1. РЕМ: обрати   ▾"; enable(remButton, true) }\n                            1 -> { townButton.text = "2. Населений пункт: обрати   ▾"; enable(townButton, true) }\n                            2 -> { streetButton.text = "3. Вулиця: обрати   ▾"; enable(streetButton, true) }\n                        }\n                        status.text = "Обери ${arrayOf("РЕМ", "населений пункт", "вулицю")[step]}"\n                    } else if (attempt < 7) {\n                        checkOptions(step, attempt + 1)\n                    } else warning("Сайт не повернув список адрес. Спробуй пізніше або обери графік за чергою.")\n                }\n            }, if (attempt == 0) 300L else 750L)\n        }\n\n        private fun showOptions(step: Int) {\n            if (closed || !loaded) return\n            evaluate(optionsScript(step)) { result ->\n                val items = choices(result)\n                if (items.isEmpty()) { warning("Список поки недоступний. Спробуй ще раз."); return@evaluate }\n                android.app.AlertDialog.Builder(this@MainActivity)\n                    .setTitle(arrayOf("Обери РЕМ", "Обери населений пункт", "Обери вулицю")[step])\n                    .setItems(items.map { it.label }.toTypedArray()) { _, at ->\n                        val selected = items[at]\n                        when (step) {\n                            0 -> {\n                                remName = selected.label\n                                townName = ""; streetName = ""; homes = emptyList()\n                                remButton.text = "1. РЕМ: $remName   ▾"\n                                townButton.text = "2. Населений пункт: завантаження…"\n                                streetButton.text = "3. Вулиця: обрати населений пункт"\n                                houseButton.text = "4. Будинок: обрати вулицю"\n                                enable(townButton, false); enable(streetButton, false); enable(houseButton, false)\n                            }\n                            1 -> {\n                                townName = selected.label\n                                streetName = ""; homes = emptyList()\n                                townButton.text = "2. Населений пункт: $townName   ▾"\n                                streetButton.text = "3. Вулиця: завантаження…"\n                                houseButton.text = "4. Будинок: обрати вулицю"\n                                enable(streetButton, false); enable(houseButton, false)\n                            }\n                            2 -> {\n                                streetName = selected.label\n                                homes = emptyList()\n                                streetButton.text = "3. Вулиця: $streetName   ▾"\n                                houseButton.text = "4. Будинок: завантаження…"\n                                enable(houseButton, false)\n                            }\n                        }\n                        generation++\n                        val token = generation\n                        val script = """(function(){try {\n                            var el=document.querySelectorAll(\'select\')[$step];\n                            if(!el)return JSON.stringify({ok:false});\n                            el.selectedIndex=${selected.index};\n                            el.dispatchEvent(new Event(\'change\',{bubbles:true}));\n                            return JSON.stringify({ok:true});\n                        }catch(e){return JSON.stringify({ok:false});}})()""".trimIndent()\n                        evaluate(script) { answer ->\n                            if (!answer.optBoolean("ok")) {\n                                warning("Сайт не прийняв вибір. Спробуй знову.")\n                            } else if (!closed && token == generation) {\n                                if (step < 2) checkOptions(step + 1, 0) else checkHouses(0)\n                            }\n                        }\n                    }\n                    .setNegativeButton("Скасувати", null).show()\n            }\n        }\n\n        private fun housesScript() = """(function(){\n            try {\n                var rows=[], tr=document.querySelectorAll(\'tr\');\n                for (var i=0;i<tr.length;i++) {\n                    var td=tr[i].querySelectorAll(\'td\');\n                    if(td.length<7)continue;\n                    var c=[];\n                    for(var j=0;j<td.length;j++) c.push((td[j].innerText||td[j].textContent||\'\').replace(/\\s+/g,\' \').trim());\n                    if (!/^[1-6]$/.test(c[4]) || !/^[12]$/.test(c[5]) || !c[3])continue;\n                    rows.push({rem:c[0],town:c[1],street:c[2],houses:c[3],group:c[4]+\'.\'+c[5],note:c[6]||\'\'});\n                }\n                return JSON.stringify({rows:rows.slice(0,500),total:rows.length});\n            }catch(e){return JSON.stringify({rows:[],error:String(e)});}\n        })()""".trimIndent()\n\n        private fun normalize(value: String): String {\n            var x = value.lowercase(Locale.ROOT).replace(Regex("\\\\s+"), " ").trim()\n            x = x.removeSuffix(" рем").trim()\n            for (prefix in arrayOf("місто ", "м. ", "село ", "с. ", "селище ", "смт. ", "смт ")) {\n                if (x.startsWith(prefix)) { x = x.removePrefix(prefix); break }\n            }\n            x = x.replace("вул. ", "вулиця ").replace("пров. ", "провулок ")\n            return x.trim()\n        }\n\n        private fun checkHouses(attempt: Int) {\n            if (closed || currentScreen != "outage_address") return\n            val token = generation\n            handler.postDelayed({\n                if (closed || token != generation || currentScreen != "outage_address") return@postDelayed\n                evaluate(housesScript()) { result ->\n                    val array = result.optJSONArray("rows")\n                    val newHomes = mutableListOf<OutageHome>()\n                    val matchRem = normalize(remName)\n                    val matchTown = normalize(townName)\n                    val matchStreet = normalize(streetName)\n                    if (array != null && result.optInt("total") <= 500) {\n                        for (i in 0 until array.length()) {\n                            val row = array.optJSONObject(i) ?: continue\n                            if (normalize(row.optString("rem")) != matchRem ||\n                                normalize(row.optString("town")) != matchTown ||\n                                normalize(row.optString("street")) != matchStreet) continue\n                            val group = row.optString("group")\n                            if (group !in OutageSchedule.VALID_GROUPS) continue\n                            val note = row.optString("note")\n                            for (house in row.optString("houses").split(Regex("[,;]"))) {\n                                val clean = house.trim()\n                                if (clean.any { it.isDigit() } && clean.length <= 30)\n                                    newHomes.add(OutageHome(clean, group, note))\n                            }\n                        }\n                    }\n                    if (newHomes.isNotEmpty()) {\n                        homes = newHomes.distinctBy { it.number + "|" + it.queue + "|" + it.note }\n                            .sortedWith(compareBy({ it.number.takeWhile { c -> c.isDigit() }.toIntOrNull() ?: Int.MAX_VALUE }, { it.number }))\n                        houseButton.text = "4. Будинок: обрати   ▾"\n                        enable(houseButton, true)\n                        status.text = "Обери номер будинку. Підчергу визначимо автоматично."\n                    } else if (attempt < 7) {\n                        checkHouses(attempt + 1)\n                    } else warning("Сайт не повернув адреси з підчергами для вибраної вулиці. Можна вибрати підчергу вручну.")\n                }\n            }, if (attempt == 0) 700L else 850L)\n        }\n\n        private fun showHouses() {\n            if (homes.isEmpty()) return\n            val labels = homes.map { home -> home.number +\n                (if (home.note.isBlank()) "" else " · ${home.note}") + " · ${home.queue}" }\n            android.app.AlertDialog.Builder(this@MainActivity)\n                .setTitle("Вибери номер будинку")\n                .setItems(labels.toTypedArray()) { _, which ->\n                    val home = homes[which]\n                    val address = "$townName, $streetName, ${home.number}"\n                    saveSelectedOutageAddress(address, home.queue)\n                }\n                .setNegativeButton("Скасувати", null).show()\n        }\n    }\n\n' + _main28[_b28:]
_main28 = one(_main28,
    '    private var outageStatus: TextView? = null',
    '    private var outageStatus: TextView? = null\n    private var currentAddressLookup: OutageAddressLookup? = null',
    '2.8: address lookup state')
_main28 = one(_main28,
    '    private fun showOutageSettingsPage() {',
    '    private fun showOutageSettingsPage() {\n        currentAddressLookup?.close()\n        currentAddressLookup = null',
    '2.8: cleanup hidden address lookup')

# A real device test confirmed normal GET-only reads do not refresh reliably.
# On the first run of 2.8, use the proven previous active mode automatically.
# Users can still change the experimental setting themselves afterwards.
_main28 = one(_main28,
    'override fun onCreate(savedInstanceState: Bundle?) { super.onCreate();',
    'override fun onCreate(savedInstanceState: Bundle?) { super.onCreate();\n'
    '        val p28 = prefs()\n'
    '        if (!p28.getBoolean("reporting_mode_28_initialized", false)) {\n'
    '            p28.edit().putBoolean("active_data_reporting_enabled", true)\n'
    '                .putBoolean("reporting_mode_28_initialized", true).apply()\n'
    '        }\n',
    '2.8: migration to tested active reporting')
_gradle28 = one(_gradle28, 'versionName = "2.7"', 'versionName = "2.8"', '2.8 version')

# Only write after every match was checked.
MAIN.write_text(_main28, encoding='utf-8')
_stats28_path.write_text(_stats28, encoding='utf-8')
GRADLE.write_text(_gradle28, encoding='utf-8')
print('OukitelMonitor 2.8: points >=5 min apart; active mode default; native address cascade')


# 2.9 — keep ONLY the reliable active telemetry mode and make the battery
# history open at approximately the last hour by default.  User can pinch to
# zoom out to the whole chosen 24h / 7d / 30d period and back in.
# This is an append to the existing 2.5-2.8 patch: no new workflow required.
_stats29_path = ROOT / 'app/src/main/java/com/oukitel/monitor/Statistics.kt'
_service29_path = ROOT / 'app/src/main/java/com/oukitel/monitor/MonitorService.kt'
_main29 = MAIN.read_text(encoding='utf-8')
_stats29 = _stats29_path.read_text(encoding='utf-8')
_service29 = _service29_path.read_text(encoding='utf-8')
_gradle29 = GRADLE.read_text(encoding='utf-8')

# Restore the known-working active-reporting command for both foreground and
# background polling, regardless of stale experimental user preferences.
# This does not turn the station's AC/DC outputs on/off.
_main29 = one(_main29,
    '''    private fun wakeCloud(s: Session) {
        if (!prefs().getBoolean("active_data_reporting_enabled", false)) return
''',
    '''    private fun wakeCloud(s: Session) {
''', '2.9: restore always-active foreground telemetry')
_service29 = one(_service29,
    '''    private fun wakeCloud(session: JSONObject) {
        if (!prefs.getBoolean("active_data_reporting_enabled", false)) return
''',
    '''    private fun wakeCloud(session: JSONObject) {
''', '2.9: restore always-active background telemetry')

# Drop the entire experimental choice UI. Preserve other settings sections,
# alerts, persisted telemetry, existing schedule and APK progress dialog.
_begin29 = '    private fun addDataRetrievalSettings(root: LinearLayout) {'
_end29 = '    private fun showSettings() {'
if _main29.count(_begin29) != 1 or _main29.count(_end29) != 1:
    raise RuntimeError('2.9: experimental settings method boundaries not found')
_a29 = _main29.index(_begin29)
_b29 = _main29.index(_end29, _a29)
_main29 = _main29[:_a29] + _main29[_b29:]
_main29 = one(_main29,
    '''        addDataRetrievalSettings(root)
        gap(root,26)
''', '', '2.9: remove experimental settings entry')
_main29 = one(_main29,
    '''        val p28 = prefs()
        if (!p28.getBoolean("reporting_mode_28_initialized", false)) {
            p28.edit().putBoolean("active_data_reporting_enabled", true)
                .putBoolean("reporting_mode_28_initialized", true).apply()
        }
''', '', '2.9: remove old experimental migration')

# The 2.4 chart keeps zoom/pan and resetZoom() shows the entire selected period.
# Show the last ~60 minutes of REAL samples whenever its data period opens.
# For histories shorter than an hour we show all available readings.
_stats29 = one(_stats29,
    '''    fun setEntries(data: List<StatisticsStore.Sample>) {
        entries = data.sortedBy { it.timestamp }
        selectedIndex = -1
        resetZoom()
    }
''',
    '''    fun showLastHour() {
        val (first, last) = limits()
        visibleEnd = last
        visibleStart = maxOf(first, last - 60.0 * 60_000.0)
        invalidate()
    }

    fun setEntries(data: List<StatisticsStore.Sample>) {
        entries = data.sortedBy { it.timestamp }
        selectedIndex = -1
        showLastHour()
    }
''', '2.9: one-hour initial chart viewport')

# Clarify how to zoom OUT and give explicit buttons for the full period and
# the most recent hour, besides the existing pinch gesture.
_main29 = one(_main29,
    '"Розведи два пальці для збільшення, проведи по графіку для переміщення."',
    '"Зведи або розведи два пальці для масштабу, проведи по графіку для переміщення."',
    '2.9: explain both zoom directions')
_main29 = one(_main29,
    '"↺   Скинути масштаб"',
    '"↔   Показати весь період"',
    '2.9: label full-period chart button')
_main29 = one(_main29,
    '''        add(root,resetScale); gap(root,18)''',
    '''        add(root,resetScale); gap(root,8)
        val hourScale = text("◷   Остання година",16f,green,true).apply {
            background=shape(panel,16,green)
            gravity=Gravity.CENTER
            setPadding(dp(15),dp(13),dp(15),dp(13))
            setOnClickListener { batteryChart.showLastHour() }
        }
        add(root,hourScale); gap(root,18)''',
    '2.9: quick return to last-hour chart view')

_gradle29 = one(_gradle29, 'versionName = "2.8"',
    'versionName = "2.9"', '2.9 version')

# Commit generated sources only once all transforms have succeeded.
MAIN.write_text(_main29, encoding='utf-8')
_service29_path.write_text(_service29, encoding='utf-8')
_stats29_path.write_text(_stats29, encoding='utf-8')
GRADLE.write_text(_gradle29, encoding='utf-8')
print('OukitelMonitor 2.9: active-only telemetry, no experiment UI, last-hour chart initially, reversible zoom')
