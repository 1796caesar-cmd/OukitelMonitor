package com.oukitel.monitor

import android.app.Activity
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.content.Context
import javax.crypto.KeyGenerator
import javax.crypto.spec.GCMParameterSpec
import java.security.KeyStore
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.graphics.*
import android.graphics.drawable.GradientDrawable
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.widget.*
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.security.MessageDigest
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.spec.IvParameterSpec
import javax.crypto.spec.SecretKeySpec
import android.util.Base64
import java.util.UUID
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : Activity() {
    private val bg = Color.rgb(5, 14, 17)
    private val panel = Color.rgb(13, 49, 43)
    private val green = Color.rgb(57, 250, 108)
    private val white = Color.WHITE
    private val muted = Color.rgb(183, 223, 202)
    private val handler = Handler(Looper.getMainLooper())
    private var session: Session? = null
    private var busy = false
    private var active = false
    private lateinit var batteryView: BatteryView
    private lateinit var batteryText: TextView
    private lateinit var inputText: TextView
    private lateinit var outputText: TextView
    private lateinit var tempText: TextView
    private lateinit var timeText: TextView
    private lateinit var statusText: TextView
    private lateinit var updatedText: TextView
    private lateinit var refresh: TextView
    private val tick = object : Runnable {
        override fun run() {
            if (active) { loadData(); handler.postDelayed(this, 5000L) }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) { super.onCreate(savedInstanceState); restoreSession(); if (android.os.Build.VERSION.SDK_INT >= 33 && checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != android.content.pm.PackageManager.PERMISSION_GRANTED) requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), 100) }
    override fun onPause() { super.onPause(); handler.removeCallbacks(tick) }
    override fun onResume() { super.onResume(); if (active) { handler.removeCallbacks(tick); loadData(); handler.postDelayed(tick, 5000L) } }
    override fun onNewIntent(intent: android.content.Intent?) { super.onNewIntent(intent); if (active && intent?.getBooleanExtra("refresh_widget",false) == true) loadData() }
    override fun onDestroy() { handler.removeCallbacks(tick); super.onDestroy() }

    private fun dp(v: Int) = (v * resources.displayMetrics.density + .5f).toInt()
    private fun shape(color: Int, radius: Int = 17, stroke: Int? = null): GradientDrawable = GradientDrawable().apply {
        colors = intArrayOf(Color.rgb(37, 105, 88), color, Color.rgb(5, 49, 30)); orientation = GradientDrawable.Orientation.TL_BR; cornerRadius = dp(radius).toFloat()
        if (stroke != null) setStroke(dp(1), stroke)
    }
    private fun text(value: String, size: Float, color: Int = white, bold: Boolean = false): TextView = TextView(this).apply {
        this.text = value; textSize = size; setTextColor(color)
        if (bold) typeface = Typeface.DEFAULT_BOLD
        gravity = Gravity.CENTER_VERTICAL
    }
    private fun column(): LinearLayout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
    private fun row(): LinearLayout = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
    private fun add(parent: LinearLayout, child: View, weight: Float = 0f, height: Int = -2) {
        parent.addView(child, LinearLayout.LayoutParams(if (weight > 0f) 0 else -1, height).apply {
            if (weight > 0f) this.weight = weight
        })
    }
    private fun gap(parent: LinearLayout, px: Int) { parent.addView(View(this), LinearLayout.LayoutParams(1, dp(px))) }

    private fun showLogin() {
        active = false; handler.removeCallbacks(tick)
        val root = column().apply { setPadding(dp(24), dp(36), dp(24), dp(24)); setBackgroundColor(bg); gravity = Gravity.CENTER_HORIZONTAL }
        gap(root, 40)
        add(root, text("ϟ", 80f, green, true).apply { gravity = Gravity.CENTER })
        gap(root, 8)
        add(root, text("OukitelMonitor", 30f, white, true).apply { gravity = Gravity.CENTER })
        add(root, text("Моніторинг зарядної станції Oukitel", 16f, muted).apply { gravity = Gravity.CENTER })
        gap(root, 32)
        fun field(hint: String, password: Boolean): EditText = EditText(this).apply {
            this.hint = hint; setSingleLine(true); textSize = 16f
            setTextColor(white); setHintTextColor(muted)
            inputType = if (password) InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD else InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS
            background = shape(panel, 18, Color.rgb(116, 222, 179)); elevation = dp(5).toFloat()
            setPadding(dp(17), dp(15), dp(17), dp(15))
        }
        val email = field("Електронна пошта Wonderfree", false)
        val password = field("Пароль", true)
        add(root, email); gap(root, 12); add(root, password); gap(root, 12)
        val region = Spinner(this)
        region.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, arrayOf("EU", "US", "CN"))
        add(root, text("Регіон хмари", 13f, muted)); add(root, region)
        gap(root, 22)
        val button = text("Увійти  →", 18f, Color.BLACK, true).apply {
            gravity = Gravity.CENTER; background = shape(Color.rgb(8, 127, 59), 18, green); elevation = dp(9).toFloat(); setPadding(0, dp(16), 0, dp(16))
        }
        add(root, button)
        gap(root, 16)
        val message = text("", 13f, muted).apply { gravity = Gravity.CENTER }
        add(root, message)
        button.setOnClickListener {
            val e = email.text.toString().trim(); val p = password.text.toString()
            if (e.isBlank() || p.isBlank()) { message.text = "Введи email і пароль"; return@setOnClickListener }
            button.isEnabled = false; message.text = "Підключення…"
            val selected = region.selectedItem.toString()
            Thread {
                try {
                    val s = connect(e, p, selected)
                    val t = readTelemetry(s)
                    runOnUiThread { session = s; saveSession(s); showDashboard(s.name); applyTelemetry(t) }
                } catch (ex: Exception) {
                    runOnUiThread { message.text = "Помилка: ${ex.message ?: "немає з’єднання"}"; button.isEnabled = true }
                }
            }.start()
        }
        setContentView(ScrollView(this).apply { isFillViewport = true; addView(root) })
    }

    private fun metric(icon: String, label: String, color: Int): Pair<LinearLayout, TextView> {
        val tile = column().apply { background = shape(panel, 23, Color.rgb(110, 215, 193)); setPadding(dp(15), dp(19), dp(12), dp(19)); elevation=dp(9).toFloat() }
        add(tile, text("$icon  $label", 16f, white, true))
        val value = text("—", 29f, white, true)
        add(tile, value)
        return Pair(tile, value)
    }

    private fun showDashboard(name: String) {
        active = true
        MonitorService.start(this)
        val root = column().apply { setBackgroundColor(bg); setPadding(dp(18), dp(22), dp(18), dp(24)) }
        val top = row()
        val heading = column()
        add(heading, text("OukitelMonitor", 21f, white, true))
        add(heading, text(name, 13f, muted))
        top.addView(heading, LinearLayout.LayoutParams(0, -2, 1f))
        val actions = row().apply { gravity = Gravity.RIGHT }
        refresh = text("⟳", 28f, green, true).apply { gravity = Gravity.CENTER; background = shape(panel, 15, green); setPadding(dp(12), dp(7), dp(12), dp(7)); elevation=dp(5).toFloat() }
        actions.addView(refresh)
        val exit = text("⇥", 27f, green, true).apply { gravity = Gravity.CENTER; background = shape(panel, 15, green); setPadding(dp(12), dp(7), dp(12), dp(7)); elevation=dp(5).toFloat() }
        actions.addView(exit, LinearLayout.LayoutParams(-2,-2).apply { leftMargin=dp(9) })
        exit.setOnClickListener { confirmLogout() }
        updatedText = text("", 10f, muted)
        top.addView(actions)
        add(root, top)
        add(root, updatedText.apply { gravity=Gravity.RIGHT })
        gap(root, 12)
        batteryView = BatteryView()
        root.addView(batteryView, LinearLayout.LayoutParams(-1, dp(295)))
        batteryText = batteryView.percent
        statusText = text("Очікування даних", 19f, green, true).apply { gravity = Gravity.CENTER; background = shape(Color.rgb(9, 71, 40), 25, green); setPadding(dp(15),dp(11),dp(15),dp(11)); elevation=dp(6).toFloat() }
        add(root, statusText)
        gap(root, 12)
        val first = row()
        val a = metric("↳", "Вхід", green); inputText = a.second
        val b = metric("↗", "Вихід", Color.rgb(255, 180, 72)); outputText = b.second
        first.addView(a.first, LinearLayout.LayoutParams(0, -2, 1f).apply { rightMargin = dp(5) })
        first.addView(b.first, LinearLayout.LayoutParams(0, -2, 1f).apply { leftMargin = dp(5) })
        add(root, first); gap(root, 10)
        val second = row()
        val c = metric("♨", "Температура", Color.CYAN); tempText = c.second
        val d = metric("◷", "Час роботи", Color.MAGENTA); timeText = d.second
        second.addView(c.first, LinearLayout.LayoutParams(0, -2, 1f).apply { rightMargin = dp(5) })
        second.addView(d.first, LinearLayout.LayoutParams(0, -2, 1f).apply { leftMargin = dp(5) })
        add(root, second); gap(root, 10)
        val alertsButton = text("🔔   Створити сповіщення     ›", 17f, white, true).apply {
            gravity = Gravity.CENTER_VERTICAL
            background = shape(Color.rgb(22, 59, 38), 20, Color.rgb(49, 116, 70))
            elevation = dp(8).toFloat()
            setPadding(dp(18), dp(20), dp(18), dp(20))
        }
        add(root, alertsButton); gap(root, 14)
        alertsButton.setOnClickListener { showAlerts() }
        
        refresh.setOnClickListener { loadData() }
        setContentView(ScrollView(this).apply { isFillViewport = true; addView(root) })
        handler.removeCallbacks(tick); handler.postDelayed(tick, 5000L)
    }

    private fun confirmLogout() {
        android.app.AlertDialog.Builder(this).setTitle("Вийти з облікового запису?")
            .setMessage("Для повторного входу знадобляться email і пароль Wonderfree.")
            .setNegativeButton("Скасувати", null)
            .setPositiveButton("Вийти") { _, _ ->
                stopService(android.content.Intent(this, MonitorService::class.java))
                session = null; prefs().edit().remove("saved_session").remove("previous_power_state").remove("previous_level").apply()
                showLogin()
            }.show()
    }

    private fun applyTelemetry(t: Telemetry) {
        batteryView.level = t.battery ?: 0
        batteryText.text = t.battery?.let { "$it%" } ?: "—%"
        inputText.text = t.input; outputText.text = t.output
        tempText.text = t.temperature; timeText.text = t.remaining
        val state = statusFor(t.inputWatts, t.outputWatts)
        statusText.text = state.second
        statusText.setTextColor(if (state.first == "outage") Color.rgb(255, 112, 112) else green)
        saveTelemetry(t)
        checkAlerts(t.battery)
        checkPowerAlerts(state.first, t.battery)
        updatedText.text = "Оновлено " + SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
    }
    private fun loadData() {
        val s = session ?: return
        if (busy || !active) return
        busy = true; refresh.text = "◌"
        Thread {
            try {
                val t = readTelemetry(s)
                runOnUiThread { if (active) applyTelemetry(t); busy = false; if (active) refresh.text = "⟳" }
            } catch (ex: Exception) {
                runOnUiThread { busy = false; if (active) { refresh.text = "⟳"; Toast.makeText(this, "Не вдалося оновити: ${ex.message}", Toast.LENGTH_LONG).show() } }
            }
        }.start()
    }

    private inner class BatteryView : android.widget.FrameLayout(this) {
        var level: Int = 0
            set(value) { field = value; invalidate() }
        val percent = text("—%", 65f, white, true).apply { gravity = Gravity.CENTER }
        init {
            setWillNotDraw(false)
            val center = column().apply { gravity = Gravity.CENTER }
            add(center, percent)
            add(center, text("Заряд батареї", 16f, Color.rgb(210, 240, 220)).apply { gravity = Gravity.CENTER })
            addView(center, android.widget.FrameLayout.LayoutParams(dp(210), dp(100), Gravity.CENTER))
        }
        override fun onDraw(canvas: Canvas) {
            super.onDraw(canvas)
            val d = resources.displayMetrics.density
            val cx = width / 2f; val cy = height / 2f
            val radius = minOf(width / 2f - 36*d, height / 2f - 30*d).coerceAtLeast(40*d)
            val p = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 26*d; strokeCap = Paint.Cap.ROUND }
            val arc = RectF(cx-radius,cy-radius,cx+radius,cy+radius)
            p.color = Color.rgb(30,62,45)
            canvas.drawArc(arc,0f,360f,false,p)
            p.color = green
            p.shader = SweepGradient(cx,cy,intArrayOf(Color.rgb(0,145,68),green,Color.rgb(133,255,168),green),null)
            canvas.drawArc(arc,-90f,360f*level.coerceIn(0,100)/100f,false,p)
            p.shader = null
        }
    }

    private data class AlertRule(val id: Long, val kind: String, val threshold: Int, val enabled: Boolean)
    private fun prefs() = getSharedPreferences("oukitel", MODE_PRIVATE)
    private fun getRules(): MutableList<AlertRule> {
        val raw = prefs().getString("rules", "[]") ?: "[]"
        val result = mutableListOf<AlertRule>()
        val arr = org.json.JSONArray(raw)
        for (i in 0 until arr.length()) {
            val x = arr.getJSONObject(i)
            result.add(AlertRule(x.optLong("id"), x.optString("kind"), x.optInt("threshold"), x.optBoolean("enabled", true)))
        }
        return result
    }
    private fun saveRules(rules: List<AlertRule>) {
        val arr = org.json.JSONArray()
        rules.forEach { r -> arr.put(JSONObject().put("id",r.id).put("kind",r.kind).put("threshold",r.threshold).put("enabled",r.enabled)) }
        prefs().edit().putString("rules",arr.toString()).apply()
    }
    private fun showAlerts() {
        active = false; handler.removeCallbacks(tick)
        val root = column().apply { setBackgroundColor(bg); setPadding(dp(20),dp(26),dp(20),dp(26)) }
        val back = text("‹   Назад",18f,green,true).apply { setPadding(0,dp(8),0,dp(8)) }
        add(root,back); back.setOnClickListener { showDashboard(session?.name ?: "P1000E Plus"); loadData() }
        gap(root,20)
        add(root,text("Сповіщення",29f,white,true)); gap(root,8)
        add(root,text("Пороги заряду та події станції",14f,muted)); gap(root,16)
        fun systemToggle(title: String, key: String): LinearLayout {
            val line = row().apply { background = shape(panel,20,Color.rgb(108,220,168)); elevation=dp(7).toFloat(); setPadding(dp(12),dp(12),dp(10),dp(12)) }
            line.addView(text(title,16f,white,true),LinearLayout.LayoutParams(0,-2,1f))
            line.addView(Switch(this).apply {
                isChecked = prefs().getBoolean(key,true)
                setOnCheckedChangeListener { _, checked -> prefs().edit().putBoolean(key,checked).apply() }
            })
            return line
        }
        add(root,systemToggle("⚡ Почалось заряджання","alert_charging")); gap(root,10)
        add(root,systemToggle("🔌 Зникла мережа","alert_outage")); gap(root,20)
        val items = column(); add(root,items)
        fun render() {
            items.removeAllViews()
            getRules().forEach { rule ->
                val row = row().apply { background=shape(panel,20,Color.rgb(108,220,168)); setPadding(dp(12),dp(10),dp(8),dp(10)); elevation=dp(3).toFloat() }
                val title = if(rule.kind=="below") "Заряд менше ${rule.threshold}%" else "Заряд досяг ${rule.threshold}%"
                row.addView(text(title,16f,white,true),LinearLayout.LayoutParams(0,-2,1f))
                val toggle = Switch(this).apply { isChecked=rule.enabled; setOnCheckedChangeListener { _,on -> saveRules(getRules().map { if(it.id==rule.id) it.copy(enabled=on) else it }) } }
                row.addView(toggle)
                val del = text("✕",22f,muted).apply { gravity=Gravity.CENTER; setPadding(dp(10),dp(8),dp(10),dp(8)) }
                row.addView(del)
                del.setOnClickListener { saveRules(getRules().filterNot { it.id==rule.id }); render() }
                add(items,row); gap(items,10)
            }
        }
        render(); gap(root,16)
        val spinner = Spinner(this).apply { adapter=ArrayAdapter(this@MainActivity,android.R.layout.simple_spinner_dropdown_item,arrayOf("Заряд менше", "Заряд досяг")) }
        add(root,spinner); gap(root,8)
        val number = EditText(this).apply { hint="Відсоток (1–100)"; inputType=InputType.TYPE_CLASS_NUMBER; setTextColor(white); setHintTextColor(muted); background=shape(panel); setPadding(dp(15),dp(14),dp(15),dp(14)) }
        add(root,number); gap(root,12)
        val create = text("＋   Додати сповіщення",17f,Color.BLACK,true).apply { gravity=Gravity.CENTER; background=shape(green,16); elevation=dp(7).toFloat(); setPadding(dp(12),dp(16),dp(12),dp(16)) }
        add(root,create)
        create.setOnClickListener {
            val threshold=number.text.toString().toIntOrNull()
            if(threshold==null || threshold !in 1..100) { Toast.makeText(this,"Вкажи число від 1 до 100",Toast.LENGTH_SHORT).show(); return@setOnClickListener }
            val kind=if(spinner.selectedItemPosition==0) "below" else "reached"
            val rules=getRules()
            if(rules.any { it.kind==kind && it.threshold==threshold }) { Toast.makeText(this,"Таке правило вже існує",Toast.LENGTH_SHORT).show(); return@setOnClickListener }
            rules.add(AlertRule(System.currentTimeMillis(),kind,threshold,true)); saveRules(rules)
            number.text.clear(); render()
        }
        setContentView(ScrollView(this).apply { isFillViewport=true; addView(root) })
    }
    private fun checkAlerts(level: Int?) {
        if(level==null) return
        val p=prefs(); val previous=p.getInt("previous_level",-1)
        if(previous>=0 && previous!=level) getRules().filter { it.enabled }.forEach { rule ->
            val crossed=if(rule.kind=="below") previous>=rule.threshold && level<rule.threshold else previous<rule.threshold && level>=rule.threshold
            if(crossed) notifyAlert(if(rule.kind=="below") "Заряд менше ${rule.threshold}%" else "Заряд досяг ${rule.threshold}%",level)
        }
        p.edit().putInt("previous_level",level).apply()
    }
    private fun statusFor(input: Double?, output: Double?): Pair<String,String> {
        if (input == null || output == null) return "unknown" to "Немає даних"
        if (input == 0.0 && output > 0.0) return "outage" to "Зникла мережа"
        if (input > output) return "charging" to "Йде заряджання"
        if (input == 0.0 && output == 0.0) return "idle" to "Очікування"
        return "balance" to "Баланс потужності"
    }
    private fun checkPowerAlerts(state: String, level: Int?) {
        if (state == "unknown") return
        val p = prefs()
        val previous = p.getString("previous_power_state",null)
        if (previous != null && previous != state) {
            if (state == "charging" && p.getBoolean("alert_charging",true)) notifyAlert("Почалось заряджання",level)
            if (state == "outage" && p.getBoolean("alert_outage",true)) notifyAlert("Зникла мережа",level)
        }
        p.edit().putString("previous_power_state",state).apply()
    }
    private fun notifyAlert(title: String, level: Int?) {
        val nm=getSystemService(android.app.NotificationManager::class.java)
        val channel="charge_alerts"
        nm.createNotificationChannel(android.app.NotificationChannel(channel,"Сповіщення заряду",android.app.NotificationManager.IMPORTANCE_HIGH))
        val notification=android.app.Notification.Builder(this,channel).setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title).setContentText(level?.let { "Поточний заряд: $it%" } ?: "Стан станції змінився").setAutoCancel(true).build()
        nm.notify((System.currentTimeMillis()%Int.MAX_VALUE).toInt(),notification)
    }
    private fun saveTelemetry(t: Telemetry) {
        prefs().edit().putInt("charge",t.battery ?: -1).putString("input",t.input).putString("output",t.output)
            .putString("temp",t.temperature).putString("remaining",t.remaining)
            .putString("updated",SimpleDateFormat("HH:mm:ss",Locale.getDefault()).format(Date())).apply()
        MonitorWidget.updateAll(this)
    }

    private fun secretKey(): javax.crypto.SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey("oukitel_session_v1", null) as? javax.crypto.SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore")
        generator.init(KeyGenParameterSpec.Builder("oukitel_session_v1",KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
        return generator.generateKey()
    }
    private fun saveSession(s: Session) {
        try {
            val raw = JSONObject().put("base",s.base).put("token",s.token).put("pk",s.pk).put("dk",s.dk).put("name",s.name).toString()
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.ENCRYPT_MODE,secretKey())
            val bytes = cipher.iv + cipher.doFinal(raw.toByteArray(Charsets.UTF_8))
            prefs().edit().putString("saved_session",Base64.encodeToString(bytes,Base64.NO_WRAP)).apply()
        } catch (_: Exception) { }
    }
    private fun restoreSession() {
        val saved = prefs().getString("saved_session",null)
        if (saved == null) { showLogin(); return }
        Thread {
            try {
                val bytes = Base64.decode(saved,Base64.NO_WRAP)
                val cipher = Cipher.getInstance("AES/GCM/NoPadding")
                cipher.init(Cipher.DECRYPT_MODE,secretKey(),GCMParameterSpec(128,bytes.copyOfRange(0,12)))
                val j = JSONObject(String(cipher.doFinal(bytes.copyOfRange(12,bytes.size)),Charsets.UTF_8))
                val s = Session(j.getString("base"),j.getString("token"),j.getString("pk"),j.getString("dk"),j.getString("name"))
                val telemetry = readTelemetry(s)
                runOnUiThread { session = s; showDashboard(s.name); applyTelemetry(telemetry) }
            } catch (_: Exception) {
                runOnUiThread { prefs().edit().remove("saved_session").apply(); showLogin() }
            }
        }.start()
    }

    private fun sha256(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }

    private data class Session(val base: String, val token: String, val pk: String, val dk: String, val name: String)
    private data class Telemetry(val battery: Int?, val input: String, val output: String, val temperature: String, val remaining: String, val inputWatts: Double?, val outputWatts: Double?)

    private fun connect(email: String, password: String, region: String): Session {
        val config = when (region) {
            "US" -> Triple("https://iot-api.quectelus.com", "pUTp5goB1bLinprRQMmK3EPiiuPiGrJtKUNptWRXVmP", "U.SP.8589934603")
            "CN" -> Triple("https://iot-gateway.quectel.com", "EufftRJSuWuVY7c6txzGifV9bJcfXHAFa7hXY5doXSn7", "C.DM.5903.1")
            else -> Triple("https://iot-api.quecteleu.com", "3aRNUwWahjyANa7WfBK2wCCkxCexB6nXxKJwXxfePvzf", "E.SP.4294967410")
        }
        val alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        val random = SecureRandom().let { rng -> (1..16).map { alphabet[rng.nextInt(alphabet.length)] }.joinToString("") }
        val md5 = MessageDigest.getInstance("MD5").digest(random.toByteArray()).joinToString("") { "%02X".format(it) }
        val key = md5.substring(8, 24)
        val iv = key.substring(8, 16) + key.substring(0, 8)
        val cipher = Cipher.getInstance("AES/CBC/PKCS5Padding")
        cipher.init(Cipher.ENCRYPT_MODE, SecretKeySpec(key.toByteArray(), "AES"), IvParameterSpec(iv.toByteArray()))
        val encPwd = Base64.encodeToString(cipher.doFinal(password.toByteArray(Charsets.UTF_8)), Base64.DEFAULT)
        val signature = sha256(email + encPwd + random + config.second)
        val fields = mapOf("pwd" to encPwd, "email" to email, "random" to random, "userDomain" to config.third, "signature" to signature)
        val form = fields.entries.joinToString("&") { (k, v) -> URLEncoder.encode(k, "UTF-8") + "=" + URLEncoder.encode(v, "UTF-8") }
        val login = request(config.first + "/v2/enduser/enduserapi/emailPwdLogin", "POST", form, null)
        val token = login.optJSONObject("data")?.optJSONObject("accessToken")?.optString("token").orEmpty()
        if (token.isBlank()) throw IllegalStateException("Вхід не підтверджено: " + login.optString("msg", "Перевір дані"))
        val devices = request(config.first + "/v2/binding/enduserapi/userDeviceList?pageNumber=1&pageSize=50", "GET", null, token)
        val list = devices.optJSONObject("data")?.optJSONArray("list") ?: throw IllegalStateException("Список пристроїв недоступний")
        val device = list.optJSONObject(0) ?: throw IllegalStateException("Станцію не знайдено")
        val pk = device.optString("productKey")
        val dk = device.optString("deviceKey")
        if (pk.isBlank() || dk.isBlank()) throw IllegalStateException("Ідентифікатори станції відсутні")
        val name = device.optString("deviceName").ifBlank { device.optString("productName").ifBlank { "P1000E Plus" } }
        return Session(config.first, token, pk, dk, name)
    }

    private fun readTelemetry(s: Session): Telemetry {
        val query = "?pk=" + URLEncoder.encode(s.pk, "UTF-8") + "&dk=" + URLEncoder.encode(s.dk, "UTF-8")
        val response = request(s.base + "/v2/binding/enduserapi/getDeviceBusinessAttributes" + query, "GET", null, s.token)
        val code = response.optInt("code", 200)
        if (code != 0 && code != 200) throw IllegalStateException(response.optString("msg", "Помилка API: $code"))
        val items = response.optJSONObject("data")?.optJSONArray("customizeTslInfo") ?: throw IllegalStateException("Показники недоступні")
        val values = mutableMapOf<Int, String>()
        for (i in 0 until items.length()) {
            val item = items.optJSONObject(i) ?: continue
            val tag = item.optInt("abId", -1)
            val value = item.optString("resourceValce", "")
            if (tag >= 0 && value.isNotBlank() && value != "null") values[tag] = value
        }
        fun number(tag: Int): Double? = values[tag]?.toDoubleOrNull()
        fun fmt(tag: Int, unit: String): String = number(tag)?.let { "${it.toInt()} $unit" } ?: "—"
        val input = number(4)
        val output = number(5)
        val remainingMinutes = number(2)?.toLong()
        val remaining = if (input != null && output != null && output > input && output > 0 && remainingMinutes != null && remainingMinutes >= 0) {
            "${remainingMinutes / 60} год ${remainingMinutes % 60} хв"
        } else "—"
        // AC input power > 0 confirms grid/AC input. Zero cannot prove a power outage.
        return Telemetry(number(1)?.toInt()?.coerceIn(0, 100), fmt(4, "Вт"), fmt(5, "Вт"), fmt(14, "°C"), remaining, input, output)
    }

    private fun request(url: String, method: String, form: String?, token: String?): JSONObject {
        val connection = URL(url).openConnection() as HttpURLConnection
        try {
            connection.requestMethod = method
            connection.connectTimeout = 10000
            connection.readTimeout = 20000
            connection.setRequestProperty("X-Q-Language", "en")
            connection.setRequestProperty("quec-random-url", UUID.randomUUID().toString())
            connection.setRequestProperty("app-info", "[Pixel][Google][raven][33]")
            if (token != null) connection.setRequestProperty("Authorization", token)
            if (form != null) {
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
                connection.outputStream.use { it.write(form.toByteArray(Charsets.UTF_8)) }
            }
            val stream = if (connection.responseCode in 200..299) connection.inputStream else connection.errorStream
            val body = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
            if (body.isBlank()) throw IllegalStateException("Порожня відповідь (HTTP ${connection.responseCode})")
            return JSONObject(body)
        } finally { connection.disconnect() }
    }
}
