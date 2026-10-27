plugins { id("com.android.application"); id("org.jetbrains.kotlin.android") }
android {
    namespace = "com.oukitel.monitor"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.oukitel.monitor"
        minSdk = 26
        targetSdk = 35
        versionCode = 14
        versionName = "1.4"
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
}
