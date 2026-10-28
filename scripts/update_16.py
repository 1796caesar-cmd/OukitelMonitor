"""Apply OukitelMonitor 1.6 upgrade after scripts/update_ui_15.py.

Keeps charge/power alert implementations unchanged. The requested update controls,
connectivity indicator, swipe refresh, battery graph and safe session handling
are applied to the current source rather than replacing the Android project.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'app/src/main/java/com/oukitel/monitor/MainActivity.kt'
SERVICE = ROOT / 'app/src/main/java/com/oukitel/monitor/MonitorService.kt'
GRADLE = ROOT / 'app/build.gradle.kts'


def replace_once(source, old, new, title):
    found = source.count(old)
    if found != 1:
        raise RuntimeError(f'{title}: expected 1 match; found {found}: {old[:85]!r}')
    return source.replace(old, new, 1)


def replace_section(source, opening, closing, replacement, title):
    i = source.find(opening)
    j = source.find(closing, i + len(opening))
    if i < 0 or j < 0 or source.find(opening, i + 1) >= 0:
        raise RuntimeError(f'{title}: section boundaries could not be identified')
    return source[:i] + replacement + source[j:]


s = MAIN.read_text(encoding='utf8')

# 1. Foreground interval, no fixed 5-second polling, and no refresh button.
s = replace_section(s,
    '    private lateinit var refresh: TextView\n',
    '    override fun onCreate(savedInstanceState: Bundle?)', '''    private lateinit var connectionText: TextView
    private var authPromptVisible = false
    private val tick = object : Runnable {
        override fun run() {
            if (active && currentScreen == "dashboard" && prefs().getBoolean("foreground_refresh_enabled", true)) {
                loadData()
                handler.postDelayed(this, foregroundIntervalMs())
            }
        }
    }
    private fun foregroundIntervalMs(): Long =
        prefs().getLong("foreground_interval_ms", 60_000L).coerceIn(5_000L, 1_800_000L)

    private val freshnessTick = object : Runnable {
        override fun run() {
            if (active && currentScreen == "dashboard") {
                if (!busy && connectionText.text.toString().contains("Дані отримано")) {
                    val age = System.currentTimeMillis() - prefs().getLong("connection_last_success", 0L)
                    val allowed = maxOf(600_000L, foregroundIntervalMs() * 2)
                    if (age > allowed) {
                        connectionText.text = "●  Дані застаріли"
                        connectionText.setTextColor(Color.rgb(244, 180, 62))
                    }
                }
                handler.postDelayed(this, 60_000L)
            }
        }
    }

    private fun scheduleForeground() {
        handler.removeCallbacks(tick)
        if (active && currentScreen == "dashboard" && prefs().getBoolean("foreground_refresh_enabled", true)) {
            handler.postDelayed(tick, foregroundIntervalMs())
        }
    }

    private fun scheduleFreshness() {
        handler.removeCallbacks(freshnessTick)
        if (active && currentScreen == "dashboard") handler.postDelayed(freshnessTick, 60_000L)
    }

''', 'foreground scheduler')
s = replace_once(s,
    'override fun onResume() { super.onResume(); if (active) { handler.removeCallbacks(tick); loadData(); handler.postDelayed(tick, 5000L) } }',
    'override fun onResume() { super.onResume(); if (active && currentScreen == "dashboard") { loadData(); scheduleForeground(); scheduleFreshness() } }',
    'resume scheduler')

s = replace_once(s,
    'override fun onPause() { super.onPause(); handler.removeCallbacks(tick) }',
    'override fun onPause() { super.onPause(); handler.removeCallbacks(tick); handler.removeCallbacks(freshnessTick) }',
    'pause freshness polling')
s = replace_once(s,
    'override fun onDestroy() { handler.removeCallbacks(tick); super.onDestroy() }',
    'override fun onDestroy() { handler.removeCallbacks(tick); handler.removeCallbacks(freshnessTick); super.onDestroy() }',
    'destroy freshness polling')

# A native ScrollView allows pull-down refresh without AndroidX or extra dependencies.
s = replace_once(s,
    '    // Built-in gradient stays stable when the soft keyboard resizes the window.',
'''    private inner class RefreshScrollView : ScrollView(this@MainActivity) {
        private var downY = 0f
        override fun onTouchEvent(event: android.view.MotionEvent): Boolean {
            if (event.actionMasked == android.view.MotionEvent.ACTION_DOWN) downY = event.y
            if (event.actionMasked == android.view.MotionEvent.ACTION_UP && scrollY == 0 && event.y - downY > dp(75)) {
                loadData()
            }
            return super.onTouchEvent(event)
        }
    }

    // Built-in gradient stays stable when the soft keyboard resizes the window.''', 'swipe-to-refresh')

# 2. Dashboard: replace only header UI and polling hooks, keep all existing cards & themes.
s = replace_once(s,
    '        MonitorService.start(this)\n',
    '''        if (prefs().getBoolean("background_refresh_enabled", true)) MonitorService.start(this)
        else stopService(Intent(this, MonitorService::class.java))
''', 'service background toggle')
s = replace_section(s,
    '        val actions = row().apply { gravity = Gravity.RIGHT }\n',
    '        gap(root, 12)\n        batteryView = BatteryView()',
'''        connectionText = text("●  Очікування даних", 13f, Color.rgb(244, 180, 62), true)
        updatedText = text(
            "Останнє оновлення: " + (prefs().getString("updated", "—") ?: "—"),
            11f, muted
        )
        add(heading, connectionText)
        add(heading, updatedText)
        add(root, top)
''', 'dashboard top bar')
s = replace_once(s,
    '        refresh.setOnClickListener { loadData() }\n        setContentView(ScrollView(this).apply { background = forestBackground(); isFillViewport = true; addView(root) })\n        handler.removeCallbacks(tick); handler.postDelayed(tick, 5000L)',
'''        setContentView(RefreshScrollView().apply { background = forestBackground(); isFillViewport = true; addView(root) })
        showCachedDashboard()
        scheduleForeground()
        scheduleFreshness()''', 'dashboard swipe and scheduling')

# A successfully fetched API response confirms cloud reachability, but not fresh
# device telemetry. Show the time of the last successful fetch explicitly.
s = replace_once(s,
    '        updatedText.text = "Оновлено $at"\n        refresh.text = "⟳  $at"',
'''        prefs().edit().putLong("connection_last_success", System.currentTimeMillis()).apply()
        updatedText.text = "Оновлено $at"
        connectionText.text = "●  Дані отримано"
        connectionText.setTextColor(Color.rgb(76, 214, 125))''', 'last update & green status')

s = replace_section(s,
    '    private fun loadData() {\n',
    '    private inner class BatteryView', '''    private fun showCachedDashboard() {
        val p = prefs()
        val level = p.getInt("charge", -1)
        if (level in 0..100) {
            batteryView.level = level
            batteryText.text = "$level%"
            inputText.text = p.getString("input", "—") ?: "—"
            outputText.text = p.getString("output", "—") ?: "—"
            tempText.text = p.getString("temp", "—") ?: "—"
            timeText.text = p.getString("remaining", "—") ?: "—"
        }
        val updated = p.getString("updated", "—") ?: "—"
        updatedText.text = "Останні дані: $updated"
        connectionText.text = "●  Очікування зв'язку"
        connectionText.setTextColor(Color.rgb(244, 180, 62))
    }

    private fun isSessionExpired(error: String): Boolean {
        val e = error.lowercase(Locale.ROOT)
        return e.contains("token validation failed") || e.contains("token expired") ||
            e.contains("invalid token") || e.contains("сесія wonderfree завершилась") ||
            e.contains("unauthorized")
    }

    private fun showSessionExpired() {
        if (authPromptVisible) return
        authPromptVisible = true
        active = false
        handler.removeCallbacks(tick)
        stopService(Intent(this, MonitorService::class.java))
        prefs().edit().remove("saved_session").apply()
        android.app.AlertDialog.Builder(this)
            .setTitle("Потрібен повторний вхід")
            .setMessage("Сесія Wonderfree закінчилась. Увійди повторно, щоб відновити моніторинг та сповіщення.")
            .setCancelable(false)
            .setPositiveButton("Увійти") { _, _ -> authPromptVisible = false; showLogin() }
            .show()
    }

    private fun loadData() {
        val s = session ?: return
        if (busy || !active || currentScreen != "dashboard") return
        busy = true
        connectionText.text = "●  Оновлення…"
        connectionText.setTextColor(Color.rgb(244, 180, 62))
        Thread {
            try {
                val telemetry = readTelemetry(s)
                runOnUiThread {
                    busy = false
                    if (active && currentScreen == "dashboard") applyTelemetry(telemetry)
                }
            } catch (ex: Exception) {
                runOnUiThread {
                    busy = false
                    if (active && currentScreen == "dashboard") {
                        if (isSessionExpired(ex.message.orEmpty())) showSessionExpired()
                        else {
                            connectionText.text = "●  Немає зв'язку"
                            connectionText.setTextColor(Color.rgb(255, 112, 112))
                            updatedText.text = "Останні дані: " + (prefs().getString("updated", "—") ?: "—")
                            Toast.makeText(this, "Не вдалося оновити: ${ex.message ?: "помилка мережі"}", Toast.LENGTH_LONG).show()
                        }
                    }
                }
            }
        }.start()
    }

''', 'foreground data + error handling')

# 3. Foreground and background controls in Settings (not in Alerts).
s = replace_once(s,
    '        addBackgroundSettings(root)\n',
    '        addRefreshSettings(root)\n        gap(root, 20)\n        addBackgroundSettings(root)\n', 'new settings panel')
s = replace_once(s,
    '    private fun addBackgroundSettings(root: LinearLayout) {',
'''    private fun addRefreshSettings(root: LinearLayout) {
        val p = prefs()
        add(root, text("Оновлення показників", 19f, white, true)); gap(root, 10)
        add(root, text("Свайп униз на головному екрані оновлює дані вручну.", 13f, muted)); gap(root, 12)

        val foregroundRow = row().apply {
            background = shape(panel, 17, green)
            setPadding(dp(14), dp(12), dp(10), dp(12))
        }
        foregroundRow.addView(text("Коли додаток відкритий", 15f, white, true),
            LinearLayout.LayoutParams(0, -2, 1f))
        val foregroundSwitch = Switch(this).apply {
            isChecked = p.getBoolean("foreground_refresh_enabled", true)
            setOnCheckedChangeListener { _, checked ->
                p.edit().putBoolean("foreground_refresh_enabled", checked).apply()
            }
        }
        foregroundRow.addView(foregroundSwitch)
        add(root, foregroundRow); gap(root, 7)

        val foregroundMs = longArrayOf(5_000L, 10_000L, 30_000L, 60_000L,
            180_000L, 300_000L, 600_000L, 900_000L, 1_800_000L)
        val foregroundLabels = arrayOf("5 секунд", "10 секунд", "30 секунд", "1 хвилина",
            "3 хвилини", "5 хвилин", "10 хвилин", "15 хвилин", "30 хвилин")
        add(root, text("Інтервал на екрані", 13f, muted))
        val foregroundSpinner = Spinner(this)
        foregroundSpinner.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, foregroundLabels)
        val selectedForeground = foregroundMs.indexOf(p.getLong("foreground_interval_ms", 60_000L)).let { if (it >= 0) it else 3 }
        foregroundSpinner.setSelection(selectedForeground)
        foregroundSpinner.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) {}
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) {
                p.edit().putLong("foreground_interval_ms", foregroundMs[position]).apply()
            }
        }
        add(root, foregroundSpinner); gap(root, 17)

        val backgroundRow = row().apply {
            background = shape(panel, 17, green)
            setPadding(dp(14), dp(12), dp(10), dp(12))
        }
        backgroundRow.addView(text("Коли додаток згорнутий", 15f, white, true),
            LinearLayout.LayoutParams(0, -2, 1f))
        val backgroundSwitch = Switch(this).apply {
            isChecked = p.getBoolean("background_refresh_enabled", true)
            setOnCheckedChangeListener { _, checked ->
                p.edit().putBoolean("background_refresh_enabled", checked).apply()
                if (checked && session != null) MonitorService.start(this@MainActivity)
                else if (!checked) stopService(Intent(this@MainActivity, MonitorService::class.java))
            }
        }
        backgroundRow.addView(backgroundSwitch)
        add(root, backgroundRow); gap(root, 7)
        add(root, text("Фоновий інтервал", 13f, muted))
        val backgroundMinutes = intArrayOf(5, 10, 15, 20, 25, 30)
        val backgroundLabels = arrayOf("5 хвилин", "10 хвилин", "15 хвилин",
            "20 хвилин", "25 хвилин", "30 хвилин")
        val backgroundSpinner = Spinner(this)
        backgroundSpinner.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, backgroundLabels)
        val selectedBackground = backgroundMinutes.indexOf(p.getInt("background_interval_minutes", 10)).let { if (it >= 0) it else 1 }
        backgroundSpinner.setSelection(selectedBackground)
        backgroundSpinner.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onNothingSelected(parent: android.widget.AdapterView<*>?) {}
            override fun onItemSelected(parent: android.widget.AdapterView<*>?, view: View?, position: Int, id: Long) {
                p.edit().putInt("background_interval_minutes", backgroundMinutes[position]).apply()
                if (p.getBoolean("background_refresh_enabled", true) && session != null)
                    MonitorService.start(this@MainActivity)
            }
        }
        add(root, backgroundSpinner); gap(root, 6)
        add(root, text("Android може затримувати фонові оновлення. Якщо їх вимкнути, сповіщення у фоні не надходитимуть.", 12f, muted))
    }

    private fun addBackgroundSettings(root: LinearLayout) {''', 'settings controls')

# 4. Statistics: keep the battery chart, remove only the consumption chart.
s = replace_section(s,
    '        add(root,text("Потужність, Вт",18f,white,true)); gap(root,8)',
    '        add(root, detail); gap(root,12)',
    '', 'remove power graph')
s = replace_once(s,
    '        powerChart.onSampleSelected = showSample\n', '', 'remove power graph tap')
s = s.replace('batteryChart.setEntries(entries); powerChart.setEntries(entries)', 'batteryChart.setEntries(entries)')
s = replace_once(s,
    'Дані записуються приблизно кожні 15 хвилин, коли працює фонова служба. Пропущені вимірювання не домальовуються.',
    'Записи зберігаються не частіше ніж раз на 15 хвилин. Пропущені вимірювання не домальовуються.',
    'statistics interval description')

# 5. Do not discard the saved session on a temporary network error.
s = replace_section(s,
    '    private fun restoreSession() {\n',
    '    private fun sha256(value: String)',
'''    private fun restoreSession() {
        val saved = prefs().getString("saved_session", null)
        if (saved == null) { showLogin(); return }
        Thread {
            try {
                val bytes = Base64.decode(saved, Base64.NO_WRAP)
                val cipher = Cipher.getInstance("AES/GCM/NoPadding")
                cipher.init(Cipher.DECRYPT_MODE, secretKey(), GCMParameterSpec(128, bytes.copyOfRange(0, 12)))
                val j = JSONObject(String(cipher.doFinal(bytes.copyOfRange(12, bytes.size)), Charsets.UTF_8))
                val s = Session(j.getString("base"), j.getString("token"), j.getString("pk"),
                    j.getString("dk"), j.getString("name"))
                runOnUiThread { session = s; showDashboard(s.name); loadData() }
            } catch (_: Exception) {
                runOnUiThread { prefs().edit().remove("saved_session").apply(); showLogin() }
            }
        }.start()
    }

''', 'restore encrypted session offline')

# 6. Auth failures are distinct from cloud outages; do not fabricate a grid signal.
s = replace_once(s,
    '        if (code != 0 && code != 200) throw IllegalStateException(response.optString("msg", "Помилка API: $code"))',
    '''        val apiMessage = response.optString("msg", "")
        if (code == 401 || code == 403 || isSessionExpired(apiMessage))
            throw IllegalStateException("Сесія Wonderfree завершилась")
        if (code != 0 && code != 200) throw IllegalStateException(apiMessage.ifBlank { "Помилка API: $code" })''',
    'token error detection')
s = replace_once(s,
    '            val stream = if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream',
    '''            val httpCode = connection.responseCode
            if (httpCode == 401 || httpCode == 403) throw IllegalStateException("Сесія Wonderfree завершилась")
            val stream = if (httpCode in 200..299) connection.inputStream else connection.errorStream''',
    'HTTP auth error detection')

MAIN.write_text(s, encoding='utf8')

# 7. Background cadence changes only. The current notification rules, state
# transitions and channel code are deliberately left alone.
s = SERVICE.read_text(encoding='utf8')
s = replace_once(s,
'''            poll()
            handler.postDelayed(this, 60_000L)''',
'''            if (!prefs.getBoolean("background_refresh_enabled", true)) {
                stopSelf()
                return
            }
            poll()
            val minutes = prefs.getInt("background_interval_minutes", 10).coerceIn(5, 30)
            handler.postDelayed(this, minutes * 60_000L)''',
    'background 5–30m timer')
s = replace_once(s,
    '    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY',
'''    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (!prefs.getBoolean("background_refresh_enabled", true)) {
            stopSelf()
            return START_NOT_STICKY
        }
        handler.removeCallbacks(tick)
        handler.post(tick)
        return START_STICKY
    }''', 'restart background timer after settings change')
s = replace_once(s,
    '        handler.post(tick)\n    }\n    override fun onStartCommand',
    '    }\n    override fun onStartCommand',
    'avoid double timer on create')
SERVICE.write_text(s, encoding='utf8')

s = GRADLE.read_text(encoding='utf8')
s = replace_once(s, 'versionCode = 14', 'versionCode = 15', 'Android version code')
s = replace_once(s, 'versionName = "1.4"', 'versionName = "1.6"', 'Android version name')
GRADLE.write_text(s, encoding='utf8')
print('OukitelMonitor 1.6 upgrade applied. Alert rules and PowerMode.kt untouched.')
