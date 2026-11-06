"""Oukitel Monitor Android 2.1: persistent, signed release APK.

Runs after all existing Android 1.5–1.10 source-update scripts. This patch
changes only Android version metadata and Gradle release signing: no activity,
background service, alerts, UI, or Wonderfree behavior is altered.

The keystore and passwords are NEVER stored in this source or the repository;
GitHub Actions provides them as environment variables from repository Secrets.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRADLE = ROOT / "app/build.gradle.kts"


def replace_exactly_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 matching pattern, found {count}")
    return source.replace(old, new, 1)


source = GRADLE.read_text(encoding="utf-8")
source = replace_exactly_once(
    source,
    'versionCode = 19',
    'versionCode = (System.getenv("OUKITEL_BUILD_CODE")?.toIntOrNull() ?: 200000)',
    "monotonically increasing Android versionCode",
)
source = replace_exactly_once(
    source, 'versionName = "1.10"', 'versionName = "2.1"',
    "user-selected Android version 2.1",
)

# release.jks was created as PKCS12 even though it has the .jks extension.
# Keep the Android applicationId identical to previous builds, otherwise Android
# will treat it as a separate app instead of an update.
signing = '''
    signingConfigs {
        create("oukitelRelease") {
            storeFile = file(System.getenv("OUKITEL_KEYSTORE_FILE") ?: "missing-release-key.jks")
            storeType = "pkcs12"
            storePassword = System.getenv("OUKITEL_STORE_PASSWORD")
            keyAlias = System.getenv("OUKITEL_KEY_ALIAS")
            keyPassword = System.getenv("OUKITEL_KEY_PASSWORD")
        }
    }
    buildTypes {
        getByName("release") {
            signingConfig = signingConfigs.getByName("oukitelRelease")
            isMinifyEnabled = false
        }
    }
'''
source = replace_exactly_once(
    source,
    '    compileOptions {',
    signing + '    compileOptions {',
    'release signing configuration',
)
if 'applicationId = "com.oukitel.monitor"' not in source:
    raise RuntimeError("applicationId unexpectedly changed; refusing to create an incompatible APK")
GRADLE.write_text(source, encoding="utf-8")
print("Oukitel Monitor 2.1: stable signing configuration, same app ID, monotonically increasing versionCode")
