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
