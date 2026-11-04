"""Oukitel Monitor 1.8: automatically re-authenticate Wonderfree.

Run AFTER update_ui_15, update_16, update_17. Keep charge/power alerts,
PowerMode and app visual theme unchanged. Accounts are AES-GCM encrypted
by Android Keystore; no credentials go into GitHub or the output APK.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'app/src/main/java/com/oukitel/monitor/MainActivity.kt'
SERVICE = ROOT / 'app/src/main/java/com/oukitel/monitor/MonitorService.kt'
AUTH = ROOT / 'app/src/main/java/com/oukitel/monitor/AutoLogin.kt'
GRADLE = ROOT / 'app/build.gradle.kts'


def exactly(src, old, new, name):
    count = src.count(old)
    if count != 1:
        raise RuntimeError(f'{name}: expected one occurrence; found {count}: {old[:110]}')
    return src.replace(old, new, 1)


main = MAIN.read_text(encoding='utf8')
service = SERVICE.read_text(encoding='utf8')
gradle = GRADLE.read_text(encoding='utf8')
if AUTH.exists():
    raise RuntimeError('AutoLogin.kt already exists. Do not apply 1.8 twice.')

# Save credentials only after a confirmed login, encrypted on the handset.
# A one-time manual sign-in is needed on installations upgrading from 1.7,
# because previous versions stored only the access token, not the password.
main = exactly(main,
    '                    val t = readTelemetry(s)',
    '                    val t = readTelemetry(s, allowRenew = false)',
    'initial login must not reuse previous account token')
main = exactly(main,
    'runOnUiThread { session = s; saveSession(s); showDashboard(s.name); applyTelemetry(t) }',
    '''runOnUiThread {
                        session = s
                        saveSession(s)
                        if (!AutoLogin.rememberCredentials(this, e, p, selected)) {
                            Toast.makeText(this, "Автовхід не вдалося увімкнути. Перевір налаштування безпеки телефона.", Toast.LENGTH_LONG).show()
                        }
                        showDashboard(s.name)
                        applyTelemetry(t)
                    }''', 'save encrypted login')

# Recover token proactively before it expires and reactively on 401/403.
# Always preserve the rest of the telemetry parser, including real AC voltage.
main = exactly(main,
    '''    private fun readTelemetry(s: Session): Telemetry {
        wakeCloud(s)
        val query =''',
    '''    private fun readTelemetry(s: Session, allowRenew: Boolean = true): Telemetry {
        var liveToken = if (allowRenew) AutoLogin.currentToken(this, s.token) else s.token
        wakeCloud(s.copy(token = liveToken))
        val query =''', 'pre-expiry renewal')

main = exactly(main,
    '''        val response = request(s.base + "/v2/binding/enduserapi/getDeviceBusinessAttributes" + query, "GET", null, s.token)
        val code = response.optInt("code", 200)''',
    '''        val url = s.base + "/v2/binding/enduserapi/getDeviceBusinessAttributes" + query
        fun fetchWithToken(token: String): JSONObject = request(url, "GET", null, token)
        var response = try {
            fetchWithToken(liveToken)
        } catch (ex: Exception) {
            if (!allowRenew || !AutoLogin.isAuthError(ex.message.orEmpty())) throw ex
            liveToken = AutoLogin.currentToken(this, liveToken, force = true)
            fetchWithToken(liveToken)
        }
        if (allowRenew && AutoLogin.isAuthResponse(response)) {
            liveToken = AutoLogin.currentToken(this, liveToken, force = true)
            response = fetchWithToken(liveToken)
        }
        val code = response.optInt("code", 200)''', 'retry failed access token')

main = exactly(main,
    '''                stopService(android.content.Intent(this, MonitorService::class.java))
                session = null; prefs().edit().remove("saved_session").remove("previous_power_state").remove("previous_level").apply()''',
    '''                stopService(android.content.Intent(this, MonitorService::class.java))
                AutoLogin.clearCredentials(this)
                session = null; prefs().edit().remove("saved_session").remove("previous_power_state").remove("previous_level").apply()''', 'clear saved password on sign-out')

# Service must renew on its own when the UI is closed. Keep its alarm code.
service = exactly(service,
    '''                wakeCloud(session)
                val query =''',
    '''                var activeToken = AutoLogin.currentToken(this, session.getString("token"))
                session.put("token", activeToken)
                wakeCloud(session)
                val query =''', 'refresh background session')
service = exactly(service,
    '''                val connection = URL(session.getString("base") + "/v2/binding/enduserapi/getDeviceBusinessAttributes" + query).openConnection() as HttpURLConnection
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
                val items =''',
    '''                val endpoint = session.getString("base") + "/v2/binding/enduserapi/getDeviceBusinessAttributes" + query
                fun getAttributes(token: String): JSONObject {
                    val connection = URL(endpoint).openConnection() as HttpURLConnection
                    try {
                        connection.connectTimeout = 10000
                        connection.readTimeout = 20000
                        connection.setRequestProperty("Authorization", token)
                        connection.setRequestProperty("X-Q-Language", "en")
                        connection.setRequestProperty("quec-random-url", UUID.randomUUID().toString())
                        connection.setRequestProperty("app-info", "[Pixel][Google][raven][33]")
                        val status = connection.responseCode
                        val body = (if (status in 200..299) connection.inputStream else connection.errorStream)
                            ?.bufferedReader()?.use { it.readText() }.orEmpty()
                        if (status == 401 || status == 403) throw IllegalStateException("Сесія Wonderfree завершилась")
                        if (status !in 200..299) throw IllegalStateException("HTTP $status")
                        if (body.isBlank()) throw IllegalStateException("Порожня відповідь Wonderfree")
                        return JSONObject(body)
                    } finally { connection.disconnect() }
                }
                var response = try {
                    getAttributes(activeToken)
                } catch (ex: Exception) {
                    if (!AutoLogin.isAuthError(ex.message.orEmpty())) throw ex
                    activeToken = AutoLogin.currentToken(this, activeToken, force = true)
                    getAttributes(activeToken)
                }
                if (AutoLogin.isAuthResponse(response)) {
                    activeToken = AutoLogin.currentToken(this, activeToken, force = true)
                    response = getAttributes(activeToken)
                }
                if (AutoLogin.isAuthResponse(response)) return@Thread
                if (response.optInt("code", 200) !in intArrayOf(0, 200)) return@Thread
                val items =''', 'background retry once on auth expiry')

gradle = exactly(gradle, 'versionCode = 16', 'versionCode = 17', 'new version code')
gradle = exactly(gradle, 'versionName = "1.7"', 'versionName = "1.8"', 'new version name')

# Source is written only after all expected patterns were validated.
AUTH.write_text(r'''package com.oukitel.monitor

import android.content.Context
import android.util.Base64
import android.security.keystore.KeyProperties
import org.json.JSONObject
import java.security.KeyStore
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.IvParameterSpec
import javax.crypto.spec.SecretKeySpec

/**
 * Login credentials remain on the Android device, encrypted by its Keystore.
 * No cloud/server beyond the existing Wonderfree endpoint is used.
 * One common lock prevents the foreground and background workers from
 * independently reauthenticating with the same credentials.
 */
object AutoLogin {
    private const val PREFS = "oukitel"
    private const val CREDENTIALS = "auto_login_credentials_v1"
    private const val ACCESS_EXPIRY = "auto_access_expiry_v1"
    private const val KEY_ALIAS = "oukitel_session_v1"
    private const val EARLY_REFRESH = 5 * 60 * 1000L

    private fun prefs(context: Context) = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    private fun key(): javax.crypto.SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        return (ks.getKey(KEY_ALIAS, null) as? javax.crypto.SecretKey)
            ?: throw IllegalStateException("Ключ сеансу Android недоступний")
    }

    private fun seal(payload: String): String {
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.ENCRYPT_MODE, key())
        return Base64.encodeToString(c.iv + c.doFinal(payload.toByteArray(Charsets.UTF_8)), Base64.NO_WRAP)
    }

    private fun unseal(encoded: String): String {
        val bytes = Base64.decode(encoded, Base64.NO_WRAP)
        if (bytes.size < 13) throw IllegalStateException("Пошкоджені дані авторизації")
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes.copyOfRange(0, 12)))
        return String(c.doFinal(bytes.copyOfRange(12, bytes.size)), Charsets.UTF_8)
    }

    /** Saves only after successful, explicit user sign-in. */
    fun rememberCredentials(context: Context, email: String, password: String, region: String): Boolean = synchronized(this) {
        return@synchronized try {
            val data = JSONObject()
                .put("email", email).put("password", password).put("region", region)
            val token = currentSavedToken(context).orEmpty()
            val expiry = decodeJwtExpiry(token).takeIf { it > 0L }
                ?: (System.currentTimeMillis() + 110 * 60 * 1000L)
            prefs(context).edit()
                .putString(CREDENTIALS, seal(data.toString()))
                .putLong(ACCESS_EXPIRY, expiry)
                .commit()
        } catch (_: Exception) { false }
    }

    fun clearCredentials(context: Context) = synchronized(this) {
        prefs(context).edit().remove(CREDENTIALS).remove(ACCESS_EXPIRY).commit()
    }

    private fun currentSavedToken(context: Context): String? {
        return try {
            val encrypted = prefs(context).getString("saved_session", null) ?: return null
            JSONObject(unseal(encrypted)).optString("token").ifBlank { null }
        } catch (_: Exception) { null }
    }

    private fun decodeJwtExpiry(token: String): Long {
        return try {
            val parts = token.substringAfter(' ').split('.')
            if (parts.size < 2) return 0L
            val b = Base64.decode(parts[1], Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
            val exp = JSONObject(String(b, Charsets.UTF_8)).optLong("exp")
            if (exp in 1L..(Long.MAX_VALUE / 1000L)) exp * 1000L else 0L
        } catch (_: Exception) { 0L }
    }

    fun isAuthError(message: String): Boolean {
        val lower = message.lowercase(java.util.Locale.ROOT)
        return lower.contains("token validation failed") || lower.contains("token expired") ||
            lower.contains("invalid token") || lower.contains("unauthorized") ||
            lower.contains("сесія wonderfree завершилась") || lower.contains("login expired") ||
            lower.contains("http 401") || lower.contains("http 403")
    }

    fun isAuthResponse(body: JSONObject): Boolean {
        val code = body.optInt("code", 200)
        return code == 401 || code == 403 || isAuthError(body.optString("msg", ""))
    }

    /**
     * Returns the latest token. Refreshes 5 min before known expiry or once
     * after an auth rejection. Temporary connection errors don't discard the
     * stored password or session. The caller performs its request/retry.
     */
    fun currentToken(context: Context, presented: String, force: Boolean = false): String = synchronized(this) {
        val p = prefs(context)
        val stored = currentSavedToken(context)
        if (!stored.isNullOrBlank() && stored != presented) return@synchronized stored
        val token = if (!stored.isNullOrBlank()) stored else presented
        val expiry = p.getLong(ACCESS_EXPIRY, 0L)
            .takeIf { it > 0L } ?: decodeJwtExpiry(token)
        if (!force && (expiry <= 0L || System.currentTimeMillis() + EARLY_REFRESH < expiry)) {
            return@synchronized token
        }
        val encoded = p.getString(CREDENTIALS, null)
            ?: return@synchronized token // Existing 1.7 installs need one manual login.
        val creds = JSONObject(unseal(encoded))
        val email = creds.getString("email")
        val password = creds.getString("password")
        val region = creds.optString("region", "EU")
        val newToken = try { login(email, password, region) }
        catch (ex: Exception) {
            // An API outage must never wipe the locally saved login.
            throw IllegalStateException("Автоматичний вхід Wonderfree не вдався: ${ex.message ?: "немає зв'язку"}", ex)
        }
        val existing = p.getString("saved_session", null)
        if (existing != null) {
            val session = JSONObject(unseal(existing))
            session.put("token", newToken)
            if (!p.edit()
                    .putString("saved_session", seal(session.toString()))
                    .putLong(ACCESS_EXPIRY, decodeJwtExpiry(newToken).takeIf { it > 0L }
                        ?: (System.currentTimeMillis() + 110 * 60 * 1000L))
                    .commit()) throw IllegalStateException("Не вдалося зберегти нову сесію Wonderfree")
        }
        newToken
    }

    private fun login(email: String, password: String, region: String): String {
        val config = when (region) {
            "US" -> Triple("https://iot-api.quectelus.com", "pUTp5goB1bLinprRQMmK3EPiiuPiGrJtKUNptWRXVmP", "U.SP.8589934603")
            "CN" -> Triple("https://iot-gateway.quectel.com", "EufftRJSuWuVY7c6txzGifV9bJcfXHAFa7hXY5doXSn7", "C.DM.5903.1")
            else -> Triple("https://iot-api.quecteleu.com", "3aRNUwWahjyANa7WfBK2wCCkxCexB6nXxKJwXxfePvzf", "E.SP.4294967410")
        }
        val alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        val random = SecureRandom().let { rng -> (1..16).map { alphabet[rng.nextInt(alphabet.length)] }.joinToString("") }
        val md5 = MessageDigest.getInstance("MD5").digest(random.toByteArray())
            .joinToString("") { "%02X".format(it) }
        val keyString = md5.substring(8, 24)
        val iv = keyString.substring(8, 16) + keyString.substring(0, 8)
        val cipher = Cipher.getInstance("AES/CBC/PKCS5Padding")
        cipher.init(Cipher.ENCRYPT_MODE, SecretKeySpec(keyString.toByteArray(), "AES"), IvParameterSpec(iv.toByteArray()))
        val encryptedPassword = Base64.encodeToString(cipher.doFinal(password.toByteArray(Charsets.UTF_8)), Base64.DEFAULT)
        val signature = MessageDigest.getInstance("SHA-256")
            .digest((email + encryptedPassword + random + config.second).toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }
        val fields = mapOf("pwd" to encryptedPassword, "email" to email, "random" to random,
            "userDomain" to config.third, "signature" to signature)
        val form = fields.entries.joinToString("&") { (k, v) ->
            URLEncoder.encode(k, "UTF-8") + "=" + URLEncoder.encode(v, "UTF-8")
        }
        val connection = URL(config.first + "/v2/enduser/enduserapi/emailPwdLogin")
            .openConnection() as HttpURLConnection
        try {
            connection.requestMethod = "POST"
            connection.connectTimeout = 10000
            connection.readTimeout = 20000
            connection.doOutput = true
            connection.setRequestProperty("X-Q-Language", "en")
            connection.setRequestProperty("quec-random-url", UUID.randomUUID().toString())
            connection.setRequestProperty("app-info", "[Pixel][Google][raven][33]")
            connection.setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
            connection.outputStream.use { it.write(form.toByteArray(Charsets.UTF_8)) }
            val responseCode = connection.responseCode
            val input = if (responseCode in 200..299) connection.inputStream else connection.errorStream
            val bodyText = input?.bufferedReader()?.use { it.readText() }.orEmpty()
            if (responseCode !in 200..299 || bodyText.isBlank()) throw IllegalStateException("HTTP $responseCode")
            val body = JSONObject(bodyText)
            if (body.optInt("code", 200) !in intArrayOf(0, 200))
                throw IllegalStateException("Вхід відхилений Wonderfree")
            val token = body.optJSONObject("data")?.optJSONObject("accessToken")?.optString("token").orEmpty()
            if (token.isBlank()) throw IllegalStateException("Wonderfree не повернув токен")
            return token
        } finally { connection.disconnect() }
    }
}
''', encoding='utf8')
MAIN.write_text(main, encoding='utf8')
SERVICE.write_text(service, encoding='utf8')
GRADLE.write_text(gradle, encoding='utf8')
print('Oukitel Monitor 1.8: automatic Wonderfree re-login enabled in UI and background; alerts unchanged')
