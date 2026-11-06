"""Android 2.2: safe GitHub Releases update check/download/system install.

Apply after update_21_signing.py. Do not touch Wonderfree auth, telemetry,
alerts, statistics, or background service.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'app/src/main/java/com/oukitel/monitor/MainActivity.kt'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'
GRADLE = ROOT / 'app/build.gradle.kts'
UPDATER = ROOT / 'app/src/main/java/com/oukitel/monitor/UpdateManager.kt'
PATHS = ROOT / 'app/src/main/res/xml/update_file_paths.xml'


def once(s: str, old: str, new: str, description: str) -> str:
    matches = s.count(old)
    if matches != 1:
        raise RuntimeError(f'{description}: expected one occurrence, found {matches}: {old[:90]}')
    return s.replace(old, new, 1)


if UPDATER.exists() or PATHS.exists():
    raise RuntimeError('UpdateManager already exists; the Android 2.2 patch must run once')

main = MAIN.read_text(encoding='utf-8')
manifest = MANIFEST.read_text(encoding='utf-8')
gradle = GRADLE.read_text(encoding='utf-8')

# Reuse MainActivity's existing settings card UI; no new dependency there.
main = once(main, '''        gap(root,26)
        val logout=text("⇥   Вийти з облікового запису"''',
'''        gap(root,26)
        settingsItem(root, "Перевірити оновлення",
            "Пошук нової версії Oukitel Monitor на GitHub") {
            UpdateManager.checkForUpdates(this, quiet = false)
        }
        val logout=text("⇥   Вийти з облікового запису"''', 'settings update button')

# This location is emitted by update_16.py and precedes the end of dashboard.
main = once(main,
'''        showCachedDashboard()
        scheduleForeground()
        scheduleFreshness()''',
'''        showCachedDashboard()
        scheduleForeground()
        scheduleFreshness()
        UpdateManager.checkDaily(this)''', 'once-daily update notice')

# After leaving Android's "Install unknown apps" permission screen, reopen
# Android's system installer using the APK we downloaded and checked.
main = once(main,
'''    private fun showLogin() {''',
'''    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == UpdateManager.UNKNOWN_SOURCES_REQUEST) {
            UpdateManager.resumePendingInstall(this)
        }
    }

    private fun showLogin() {''', 'return from unknown-apps permission')

gradle = once(gradle,
    'versionName = "2.1"', 'versionName = "2.2"', 'Android 2.2 version')
# VersionCode is still assigned by the 2.1 signing workflow; do not reset it.
gradle = once(gradle,
'''    kotlinOptions { jvmTarget = "17" }
}''',
'''    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation("androidx.core:core:1.15.0")
}''', 'AndroidX FileProvider dependency')

manifest = once(manifest,
'''    <uses-permission android:name="android.permission.INTERNET"/>''',
'''    <uses-permission android:name="android.permission.INTERNET"/>
    <uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES"/>''',
    'Android package install permission')
manifest = once(manifest,
'''        <service android:name=".MonitorService"''',
'''        <provider
            android:name="androidx.core.content.FileProvider"
            android:authorities="${applicationId}.updates"
            android:exported="false"
            android:grantUriPermissions="true">
            <meta-data android:name="android.support.FILE_PROVIDER_PATHS"
                android:resource="@xml/update_file_paths"/>
        </provider>
        <service android:name=".MonitorService"''', 'APK read-only content provider')

# Validate all expected changes before modifying the repository.
if 'applicationId = "com.oukitel.monitor"' not in gradle:
    raise RuntimeError('Android application ID changed unexpectedly')

updater = r'''package com.oukitel.monitor

import android.app.Activity
import android.app.AlertDialog
import android.content.ClipData
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.core.content.FileProvider
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.util.Locale
import java.util.concurrent.atomic.AtomicBoolean

/** Read-only update discovery and opt-in installer via this project's public GitHub Releases. */
object UpdateManager {
    const val UNKNOWN_SOURCES_REQUEST = 7202
    private const val API = "https://api.github.com/repos/1796caesar-cmd/OukitelMonitor/releases/latest"
    private const val GITHUB_ASSETS = "https://github.com/1796caesar-cmd/OukitelMonitor/releases/download/"
    private const val PREFS = "oukitel"
    private const val PENDING_INSTALL = "pending_update_install"
    private val checking = AtomicBoolean(false)
    private val downloading = AtomicBoolean(false)

    private data class Release(val version: String, val url: String, val size: Long, val digest: String)

    /** Uses numeric version segments, not text sorting (2.10 > 2.9). */
    private fun isNewer(remote: String, local: String): Boolean {
        val a = remote.split('.').mapNotNull { it.toIntOrNull() }
        val b = local.split('.').mapNotNull { it.toIntOrNull() }
        if (a.isEmpty() || b.isEmpty()) return false
        for (i in 0 until maxOf(a.size, b.size)) {
            val v = a.getOrElse(i) { 0 }
            val old = b.getOrElse(i) { 0 }
            if (v != old) return v > old
        }
        return false
    }

    private fun getLocalVersion(activity: Activity): String =
        activity.packageManager.getPackageInfo(activity.packageName, 0).versionName ?: "0.0"

    fun checkDaily(activity: Activity) {
        val prefs = activity.getSharedPreferences(PREFS, Activity.MODE_PRIVATE)
        val now = System.currentTimeMillis()
        val last = prefs.getLong("update_last_check_ms", 0L)
        if (now - last < 24L * 60 * 60 * 1000) return
        prefs.edit().putLong("update_last_check_ms", now).apply()
        checkForUpdates(activity, quiet = true)
    }

    fun checkForUpdates(activity: Activity, quiet: Boolean) {
        if (!checking.compareAndSet(false, true)) {
            if (!quiet) Toast.makeText(activity, "Перевірка вже виконується", Toast.LENGTH_SHORT).show()
            return
        }
        if (!quiet) Toast.makeText(activity, "Перевіряю GitHub Releases…", Toast.LENGTH_SHORT).show()
        Thread {
            try {
                val connection = URL(API).openConnection() as HttpURLConnection
                val releaseJson = try {
                    connection.connectTimeout = 12000
                    connection.readTimeout = 20000
                    connection.setRequestProperty("Accept", "application/vnd.github+json")
                    connection.setRequestProperty("User-Agent", "OukitelMonitor-Android")
                    val http = connection.responseCode
                    if (http == 404) throw IllegalStateException("Поки немає опублікованих версій")
                    if (http != 200) throw IllegalStateException("GitHub недоступний (HTTP $http)")
                    JSONObject(connection.inputStream.bufferedReader().use { it.readText() })
                } finally { connection.disconnect() }
                if (releaseJson.optBoolean("draft") || releaseJson.optBoolean("prerelease")) {
                    throw IllegalStateException("Останній реліз ще не опублікований")
                }
                val rawTag = releaseJson.optString("tag_name", "")
                val version = rawTag.removePrefix("v")
                if (!Regex("""\d+(?:\.\d+){1,3}""").matches(version)) {
                    throw IllegalStateException("Невідомий формат версії")
                }
                val installed = getLocalVersion(activity)
                if (!isNewer(version, installed)) {
                    if (!quiet) activity.runOnUiThread {
                        AlertDialog.Builder(activity).setTitle("Оновлень немає")
                            .setMessage("Встановлено Oukitel Monitor $installed. Це актуальна версія.")
                            .setPositiveButton("Добре", null).show()
                    }
                    return@Thread
                }
                val expectedName = "OukitelMonitor-$version.apk"
                val assets = releaseJson.optJSONArray("assets")
                    ?: throw IllegalStateException("У GitHub Releases немає APK")
                var asset: JSONObject? = null
                for (i in 0 until assets.length()) {
                    val candidate = assets.optJSONObject(i) ?: continue
                    if (candidate.optString("name") == expectedName) { asset = candidate; break }
                }
                val selected = asset ?: throw IllegalStateException("Файл $expectedName ще не опубліковано")
                val assetUrl = selected.optString("browser_download_url", "")
                val safePrefix = "$GITHUB_ASSETS$rawTag/"
                if (assetUrl != safePrefix + expectedName) {
                    throw IllegalStateException("Некоректне посилання на оновлення")
                }
                val size = selected.optLong("size", 0L)
                if (size !in 100_000L..150_000_000L) throw IllegalStateException("Некоректний розмір APK")
                val digest = selected.optString("digest", "")
                if (!Regex("""sha256:[0-9a-fA-F]{64}""").matches(digest)) {
                    throw IllegalStateException("GitHub не повернув SHA-256 оновлення")
                }
                val release = Release(version, assetUrl, size, digest.substringAfter(':').lowercase(Locale.ROOT))
                activity.runOnUiThread {
                    AlertDialog.Builder(activity)
                        .setTitle("Доступне оновлення $version")
                        .setMessage("Установлено: $installed\nНова версія: $version\n\nЗавантажити підписаний APK з нашого GitHub?")
                        .setNegativeButton("Пізніше", null)
                        .setPositiveButton("Завантажити") { _, _ -> downloadAndInstall(activity, release) }
                        .show()
                }
            } catch (ex: Exception) {
                if (!quiet) activity.runOnUiThread {
                    AlertDialog.Builder(activity).setTitle("Не вдалося перевірити оновлення")
                        .setMessage(ex.message ?: "Немає відповіді")
                        .setPositiveButton("Добре", null).show()
                }
            } finally { checking.set(false) }
        }.start()
    }

    private fun downloadAndInstall(activity: Activity, release: Release) {
        if (!downloading.compareAndSet(false, true)) return
        val progress = ProgressBar(activity, null, android.R.attr.progressBarStyleHorizontal)
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
        dialog.show()
        Thread {
            val folder = File(activity.cacheDir, "updates")
            val file = File(folder, "OukitelMonitor-${release.version}.apk")
            val temp = File(folder, ".OukitelMonitor-${release.version}.part")
            try {
                folder.mkdirs()
                if (temp.exists()) temp.delete()
                val url = URL(release.url)
                if (url.protocol != "https" || url.host != "github.com") {
                    throw IllegalStateException("Джерело APK не підтверджене")
                }
                val connection = url.openConnection() as HttpURLConnection
                val bytes = try {
                    connection.connectTimeout = 15000
                    connection.readTimeout = 30000
                    connection.setRequestProperty("User-Agent", "OukitelMonitor-Android")
                    if (connection.responseCode != 200) throw IllegalStateException("APK не завантажився (HTTP ${connection.responseCode})")
                    val hash = MessageDigest.getInstance("SHA-256")
                    var total = 0L
                    var shown = -1
                    connection.inputStream.use { input ->
                        temp.outputStream().use { output ->
                            val buffer = ByteArray(64 * 1024)
                            while (true) {
                                val got = input.read(buffer)
                                if (got < 0) break
                                total += got
                                if (total > release.size || total > 150_000_000L) throw IllegalStateException("Завеликий APK")
                                output.write(buffer, 0, got)
                                hash.update(buffer, 0, got)
                                val pct = (total * 100 / release.size).toInt()
                                if (pct != shown && pct % 5 == 0) {
                                    shown = pct
                                    activity.runOnUiThread {
                                        progress.progress = pct
                                        label.text = "Завантаження: $pct%"
                                    }
                                }
                            }
                        }
                    }
                    if (total != release.size) throw IllegalStateException("APK завантажився не повністю")
                    val actual = hash.digest().joinToString("") { "%02x".format(it) }
                    if (actual != release.digest) throw IllegalStateException("Контрольна сума APK не збігається")
                    total
                } finally { connection.disconnect() }
                if (bytes < 100_000) throw IllegalStateException("APK занадто малий")
                if (file.exists()) file.delete()
                if (!temp.renameTo(file)) throw IllegalStateException("Не вдалося зберегти APK")
                // The installer will also enforce the original app signing key.
                val archive = activity.packageManager.getPackageArchiveInfo(file.absolutePath, 0)
                    ?: throw IllegalStateException("Неправильний формат APK")
                if (archive.packageName != activity.packageName) {
                    throw IllegalStateException("Це APK іншого додатка")
                }
                val current = activity.packageManager.getPackageInfo(activity.packageName, 0)
                val currentCode = if (Build.VERSION.SDK_INT >= 28) current.longVersionCode else current.versionCode.toLong()
                val candidateCode = if (Build.VERSION.SDK_INT >= 28) archive.longVersionCode else archive.versionCode.toLong()
                if (candidateCode <= currentCode) {
                    throw IllegalStateException("Ця збірка не новіша за встановлену")
                }
                activity.runOnUiThread {
                    dialog.dismiss()
                    prepareInstall(activity, file)
                }
            } catch (ex: Exception) {
                temp.delete()
                activity.runOnUiThread {
                    dialog.dismiss()
                    AlertDialog.Builder(activity).setTitle("Оновлення не вдалося")
                        .setMessage(ex.message ?: "Немає відповіді")
                        .setPositiveButton("Добре", null).show()
                }
            } finally { downloading.set(false) }
        }.start()
    }

    private fun prepareInstall(activity: Activity, file: File) {
        if (Build.VERSION.SDK_INT >= 26 && !activity.packageManager.canRequestPackageInstalls()) {
            activity.getSharedPreferences(PREFS, Activity.MODE_PRIVATE)
                .edit().putString(PENDING_INSTALL, file.absolutePath).apply()
            AlertDialog.Builder(activity)
                .setTitle("Дозвіл на встановлення")
                .setMessage("Android має дозволити встановлення оновлень із Oukitel Monitor. Це потрібно зробити один раз.")
                .setNegativeButton("Пізніше", null)
                .setPositiveButton("Дозволити") { _, _ ->
                    try {
                        activity.startActivityForResult(
                            Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                                Uri.parse("package:${activity.packageName}")),
                            UNKNOWN_SOURCES_REQUEST)
                    } catch (_: Exception) {
                        Toast.makeText(activity, "Відкрий дозвіл встановлення для Oukitel Monitor у налаштуваннях Android", Toast.LENGTH_LONG).show()
                    }
                }.show()
            return
        }
        install(activity, file)
    }

    fun resumePendingInstall(activity: Activity) {
        if (Build.VERSION.SDK_INT >= 26 && !activity.packageManager.canRequestPackageInstalls()) return
        val prefs = activity.getSharedPreferences(PREFS, Activity.MODE_PRIVATE)
        val path = prefs.getString(PENDING_INSTALL, null) ?: return
        prefs.edit().remove(PENDING_INSTALL).apply()
        val folder = File(activity.cacheDir, "updates").canonicalFile
        val file = File(path).canonicalFile
        if (!file.isFile || file.parentFile != folder || !file.name.matches(Regex("""OukitelMonitor-\d+(?:\.\d+){1,3}\.apk"""))) return
        install(activity, file)
    }

    private fun install(activity: Activity, file: File) {
        try {
            val uri = FileProvider.getUriForFile(activity, "${activity.packageName}.updates", file)
            val intent = Intent(Intent.ACTION_VIEW).apply {
                setDataAndType(uri, "application/vnd.android.package-archive")
                clipData = ClipData.newRawUri("OukitelMonitor", uri)
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            }
            activity.startActivity(intent)
        } catch (ex: Exception) {
            AlertDialog.Builder(activity).setTitle("Не вдалося відкрити встановлення")
                .setMessage(ex.message ?: "Перевір налаштування Android")
                .setPositiveButton("Добре", null).show()
        }
    }
}
'''
paths = '''<?xml version="1.0" encoding="utf-8"?>
<paths xmlns:android="http://schemas.android.com/apk/res/android">
    <cache-path name="updates" path="updates/"/>
</paths>
'''

MAIN.write_text(main, encoding='utf-8')
MANIFEST.write_text(manifest, encoding='utf-8')
GRADLE.write_text(gradle, encoding='utf-8')
UPDATER.write_text(updater, encoding='utf-8')
PATHS.parent.mkdir(parents=True, exist_ok=True)
PATHS.write_text(paths, encoding='utf-8')
print('Oukitel Monitor 2.2: check GitHub Releases, SHA-256 download, user-approved Android install')
