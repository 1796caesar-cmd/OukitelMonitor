package com.oukitel.monitor

import android.app.Activity
import android.os.Bundle
import android.graphics.Color
import android.text.InputType
import android.view.Gravity
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

class MainActivity : Activity() {
    private val green = Color.rgb(125, 226, 158)
    private val white = Color.WHITE
    private lateinit var status: TextView
    private lateinit var loginButton: Button
    private lateinit var refreshButton: Button
    private var lastEmail = ""
    private var lastPassword = ""
    private var lastRegion = "EU"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(38, 48, 38, 38)
            setBackgroundColor(Color.rgb(16, 30, 28))
        }
        fun label(s: String, size: Float, color: Int): TextView = TextView(this).apply {
            text = s; textSize = size; setTextColor(color)
            gravity = Gravity.CENTER; setPadding(0, 12, 0, 12)
        }
        root.addView(label("OukitelMonitor", 29f, white))
        root.addView(label("Wonderfree · Моніторинг 0.3", 16f, green))
        val email = EditText(this).apply {
            hint = "Email Wonderfree"; setSingleLine(true)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS
            setTextColor(white); setHintTextColor(Color.LTGRAY)
        }
        val password = EditText(this).apply {
            hint = "Пароль Wonderfree"; setSingleLine(true)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            setTextColor(white); setHintTextColor(Color.LTGRAY)
        }
        val region = Spinner(this)
        val regions = arrayOf("EU", "US", "CN")
        region.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, regions)
        root.addView(email); root.addView(password)
        root.addView(label("Регіон хмари (зазвичай EU)", 14f, white))
        root.addView(region)
        loginButton = Button(this).apply { text = "Підключитися" }
        root.addView(loginButton)
        refreshButton = Button(this).apply { text = "Оновити дані"; isEnabled = false }
        root.addView(refreshButton)
        status = label("Введи дані Wonderfree, щоб отримати показники. Пароль не записується на диск.", 15f, white)
        root.addView(status)
        setContentView(ScrollView(this).apply { addView(root) })
        loginButton.setOnClickListener {
            val e = email.text.toString().trim()
            val p = password.text.toString()
            if (e.isBlank() || p.isBlank()) { status.text = "Введи email і пароль"; return@setOnClickListener }
            lastEmail = e
            lastPassword = p
            lastRegion = regions[region.selectedItemPosition]
            loginButton.isEnabled = false
            refreshButton.isEnabled = false
            status.text = "Підключення до Wonderfree…"
            val selected = regions[region.selectedItemPosition]
            Thread {
                val result = try { testConnection(e, p, selected) }
                    catch (ex: Exception) { "Помилка: ${ex.message ?: ex.javaClass.simpleName}" }
                runOnUiThread { status.text = result; loginButton.isEnabled = true; refreshButton.isEnabled = true }
            }.start()
        }
        refreshButton.setOnClickListener {
            if (lastEmail.isBlank() || lastPassword.isBlank()) return@setOnClickListener
            loginButton.isEnabled = false
            refreshButton.isEnabled = false
            status.text = "Оновлюю показники…"
            Thread {
                val result = try { testConnection(lastEmail, lastPassword, lastRegion) }
                    catch (ex: Exception) { "Помилка: ${ex.message ?: ex.javaClass.simpleName}" }
                runOnUiThread { status.text = result; loginButton.isEnabled = true; refreshButton.isEnabled = true }
            }.start()
        }
    }

    private fun sha256(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }

    private fun testConnection(email: String, password: String, region: String): String {
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
        val encrypted = cipher.doFinal(password.toByteArray(Charsets.UTF_8))
        // Android Base64.DEFAULT mirrors the vendor app's wrapped base64 with trailing newline.
        val encPwd = Base64.encodeToString(encrypted, Base64.DEFAULT)
        val signature = sha256(email + encPwd + random + config.second)
        val fields = mapOf("pwd" to encPwd, "email" to email, "random" to random,
            "userDomain" to config.third, "signature" to signature)
        val form = fields.entries.joinToString("&") { (k, v) ->
            URLEncoder.encode(k, "UTF-8") + "=" + URLEncoder.encode(v, "UTF-8")
        }
        val login = request(config.first + "/v2/enduser/enduserapi/emailPwdLogin", "POST", form, null)
        val token = login.optJSONObject("data")?.optJSONObject("accessToken")?.optString("token").orEmpty()
        if (token.isBlank()) return "Вхід не підтверджено. Перевір регіон і дані облікового запису. Код: ${login.optString("code", "?")}; повідомлення: ${login.optString("msg", "невідоме")}".take(350)
        val devices = request(config.first + "/v2/binding/enduserapi/userDeviceList?pageNumber=1&pageSize=50", "GET", null, token)
        val list = devices.optJSONObject("data")?.optJSONArray("list")
            ?: return "Авторизація успішна, але список пристроїв недоступний."
        if (list.length() == 0) return "Авторизація успішна! Але станцій у цьому обліковому записі не знайдено."
        val names = (0 until list.length()).map { index ->
            val d = list.optJSONObject(index)
            d?.optString("deviceName")?.takeIf { it.isNotBlank() }
                ?: d?.optString("productName")?.takeIf { it.isNotBlank() }
                ?: "Пристрій ${index + 1}"
        }
        val device = list.optJSONObject(0) ?: return "Не вдалося прочитати дані станції"
        val pk = device.optString("productKey")
        val dk = device.optString("deviceKey")
        if (pk.isBlank() || dk.isBlank()) return "Станцію знайдено, але немає її ідентифікаторів"
        val query = "?pk=" + URLEncoder.encode(pk, "UTF-8") + "&dk=" + URLEncoder.encode(dk, "UTF-8")
        val attributes = request(config.first + "/v2/binding/enduserapi/getDeviceBusinessAttributes" + query, "GET", null, token)
        val code = attributes.optInt("code", 200)
        if (code != 0 && code != 200) return "Станцію знайдено: ${names[0]}\nХмара не повернула показники: " + attributes.optString("msg", "код $code")
        val items = attributes.optJSONObject("data")?.optJSONArray("customizeTslInfo")
            ?: return "Станцію знайдено: ${names[0]}\nСписок показників відсутній у відповіді хмари."
        val values = mutableMapOf<Int, String>()
        for (i in 0 until items.length()) {
            val item = items.optJSONObject(i) ?: continue
            val tag = item.optInt("abId", -1)
            val value = item.optString("resourceValce", "")
            if (tag >= 0 && value.isNotBlank() && value != "null") values[tag] = value
        }
        fun value(tag: Int, unit: String): String {
            val raw = values[tag] ?: return "—"
            val number = raw.toDoubleOrNull() ?: return raw
            return (if (number % 1.0 == 0.0) number.toLong().toString() else number.toString()) + unit
        }
        return "${names[0]}\n🔋 Заряд: ${value(1, "%")}\n⚡ Вхід: ${value(4, " Вт")}\n🔌 Вихід: ${value(5, " Вт")}\n\nОтримано полів: ${values.size}. Натисни «Оновити дані», щоб перевірити ще раз."
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
            if (body.isBlank()) throw IllegalStateException("Сервер повернув порожню відповідь (HTTP ${connection.responseCode})")
            return JSONObject(body)
        } finally { connection.disconnect() }
    }
}
