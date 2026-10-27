package com.oukitel.monitor

import android.app.Activity
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
    private val panel = Color.rgb(17, 29, 33)
    private val green = Color.rgb(48, 242, 106)
    private val white = Color.WHITE
    private val muted = Color.rgb(145, 163, 171)
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
    private lateinit var mainsText: TextView
    private lateinit var updatedText: TextView
    private lateinit var refresh: TextView
    private val tick = object : Runnable {
        override fun run() {
            if (active) { loadData(); handler.postDelayed(this, 30000L) }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) { super.onCreate(savedInstanceState); showLogin() }
    override fun onPause() { super.onPause(); handler.removeCallbacks(tick) }
    override fun onResume() { super.onResume(); if (active) { handler.removeCallbacks(tick); handler.postDelayed(tick, 30000L) } }
    override fun onDestroy() { handler.removeCallbacks(tick); super.onDestroy() }

    private fun dp(v: Int) = (v * resources.displayMetrics.density + .5f).toInt()
    private fun shape(color: Int, radius: Int = 17, stroke: Int? = null): GradientDrawable = GradientDrawable().apply {
        setColor(color); cornerRadius = dp(radius).toFloat()
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
        add(root, text("ϟ", 66f, green, true).apply { gravity = Gravity.CENTER })
        gap(root, 8)
        add(root, text("Вхід у Wonderfree", 29f, white, true).apply { gravity = Gravity.CENTER })
        add(root, text("Моніторинг зарядної станції", 15f, muted).apply { gravity = Gravity.CENTER })
        gap(root, 32)
        fun field(hint: String, password: Boolean): EditText = EditText(this).apply {
            this.hint = hint; setSingleLine(true); textSize = 16f
            setTextColor(white); setHintTextColor(muted)
            inputType = if (password) InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD else InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS
            background = shape(panel, 14, Color.rgb(35, 55, 57))
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
            gravity = Gravity.CENTER; background = shape(green, 15); setPadding(0, dp(16), 0, dp(16))
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
                    runOnUiThread { session = s; showDashboard(s.name); applyTelemetry(t) }
                } catch (ex: Exception) {
                    runOnUiThread { message.text = "Помилка: ${ex.message ?: "немає з’єднання"}"; button.isEnabled = true }
                }
            }.start()
        }
        setContentView(ScrollView(this).apply { fillViewport = true; addView(root) })
    }

    private fun metric(icon: String, label: String, color: Int): Pair<LinearLayout, TextView> {
        val tile = column().apply { background = shape(panel); setPadding(dp(14), dp(12), dp(10), dp(12)) }
        add(tile, text("$icon   $label", 13f, muted))
        val value = text("—", 20f, white, true)
        add(tile, value)
        return Pair(tile, value)
    }

    private fun showDashboard(name: String) {
        active = true
        val root = column().apply { setBackgroundColor(bg); setPadding(dp(18), dp(22), dp(18), dp(24)) }
        val top = row()
        val heading = column()
        add(heading, text("Моніторинг станції", 22f, white, true))
        add(heading, text(name, 13f, muted))
        top.addView(heading, LinearLayout.LayoutParams(0, -2, 1f))
        val actions = column().apply { gravity = Gravity.RIGHT }
        refresh = text("⟳", 30f, green, true).apply { gravity = Gravity.CENTER; setPadding(dp(10), 0, dp(10), 0) }
        actions.addView(refresh)
        updatedText = text("Ще не оновлено", 10f, muted).apply { gravity = Gravity.RIGHT }
        actions.addView(updatedText)
        top.addView(actions)
        add(root, top)
        gap(root, 12)
        batteryView = BatteryView()
        root.addView(batteryView, LinearLayout.LayoutParams(-1, dp(295)))
        batteryText = batteryView.percent
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
        val network = column().apply { background = shape(panel); setPadding(dp(14), dp(13), dp(14), dp(13)) }
        add(network, text("⚡  Електромережа 230 В", 14f, muted))
        mainsText = text("Перевіряємо…", 17f, green, true)
        add(network, mainsText)
        add(root, network); gap(root, 13)
        val logout = text("Вийти з облікового запису", 12f, muted).apply { gravity = Gravity.CENTER }
        add(root, logout)
        logout.setOnClickListener { session = null; showLogin() }
        refresh.setOnClickListener { loadData() }
        setContentView(ScrollView(this).apply { fillViewport = true; addView(root) })
        handler.removeCallbacks(tick); handler.postDelayed(tick, 30000L)
    }

    private fun applyTelemetry(t: Telemetry) {
        batteryView.level = t.battery ?: 0
        batteryText.text = t.battery?.let { "$it%" } ?: "—%"
        inputText.text = t.input; outputText.text = t.output
        tempText.text = t.temperature; timeText.text = t.remaining
        mainsText.text = t.mains
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
        val percent = text("—%", 54f, white, true).apply { gravity = Gravity.CENTER }
        init {
            setWillNotDraw(false)
            val center = column().apply { gravity = Gravity.CENTER }
            add(center, percent)
            add(center, text("Рівень заряду", 13f, Color.rgb(210, 240, 220)).apply { gravity = Gravity.CENTER })
            addView(center, android.widget.FrameLayout.LayoutParams(dp(210), dp(100), Gravity.CENTER))
        }
        override fun onDraw(canvas: Canvas) {
            super.onDraw(canvas)
            val cx = width / 2f; val density = resources.displayMetrics.density
            val w = 162f * density; val h = 252f * density
            val left = cx - w / 2; val top = (height - h) / 2f + 7 * density
            val rect = RectF(left, top, left + w, top + h)
            val p = Paint(Paint.ANTI_ALIAS_FLAG)
            p.color = Color.rgb(55, 77, 75); p.style = Paint.Style.FILL
            canvas.drawRoundRect(RectF(cx - 22*density, top - 13*density, cx + 22*density, top + 7*density), 7*density, 7*density, p)
            p.color = Color.rgb(11, 32, 31); canvas.drawRoundRect(rect, 22*density, 22*density, p)
            p.color = Color.rgb(142, 166, 163); p.style = Paint.Style.STROKE; p.strokeWidth = 3*density
            canvas.drawRoundRect(rect, 22*density, 22*density, p)
            p.style = Paint.Style.FILL
            val inner = RectF(rect.left + 8*density, rect.top + 8*density, rect.right - 8*density, rect.bottom - 8*density)
            val fillHeight = inner.height() * level.coerceIn(0,100) / 100f
            if (fillHeight > 0f) {
                canvas.save(); val path = Path().apply { addRoundRect(inner, 16*density, 16*density, Path.Direction.CW) }
                canvas.clipPath(path)
                p.shader = LinearGradient(inner.left, inner.bottom, inner.right, inner.top, intArrayOf(Color.rgb(0, 118, 57), Color.rgb(38, 248, 85), Color.rgb(130, 255, 137)), null, Shader.TileMode.CLAMP)
                canvas.drawRect(inner.left, inner.bottom-fillHeight, inner.right, inner.bottom, p)
                p.shader = null; canvas.restore()
            }
        }
    }

    private fun sha256(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }

    private data class Session(val base: String, val token: String, val pk: String, val dk: String, val name: String)
    private data class Telemetry(val battery: Int?, val input: String, val output: String, val temperature: String, val remaining: String, val mains: String)

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
        val acInput = number(11)
        val mains = if (acInput != null && acInput > 0) "Є живлення AC" else "Невідомо"
        return Telemetry(number(1)?.toInt()?.coerceIn(0, 100), fmt(4, "Вт"), fmt(5, "Вт"), fmt(14, "°C"), remaining, mains)
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
