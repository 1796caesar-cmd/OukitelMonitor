OUKITEL MONITOR 2.1 — APK із постійним підписом

1. У Github-репозиторії https://github.com/1796caesar-cmd/OukitelMonitor
   відкрий Settings -> Secrets and variables -> Actions.
2. Створи там 4 Repository secrets з ТИМИ САМИМИ значеннями, які вже
   використовуються для підпису MalinForest:

   MALINFOREST_KEYSTORE_BASE64  = увесь вміст C:\MalinForestKey\keystore-base64.txt
   MALINFOREST_STORE_PASSWORD  = пароль keystore, який вводив під час його створення
   MALINFOREST_KEY_ALIAS       = malinforest
   MALINFOREST_KEY_PASSWORD    = пароль ключа (той, який був при створенні)

   ВАЖЛИВО: Секрети одного GitHub-репозиторію не копіюються в інший автоматично.
   Сам файл .jks, пароль і Base64-текст НЕ додавай до файлів GitHub!

3. У github.dev завантаж:
   .github/workflows/build-apk.yml  (замінити існуючий)
   scripts/update_21_signing.py    (новий файл)
   Зроби Commit & Push.

4. Перевір Actions -> Build Android APK -> Artifacts ->
   OukitelMonitor-2.1-signed-APK. У ZIP буде app-release.apk.

5. При ПЕРШІЙ зміні debug-підпису на постійний release-підпис Android,
   найімовірніше, не дозволить встановлення поверх попереднього APK.
   Збережи важливі налаштування/правила. Може знадобитися один раз видалити
   раніше встановлений debug-додаток і встановити app-release.apk.
   Видалення додатка стирає його локальні дані, історію та облікову сесію.
   Надалі підписаний тим самим ключем APK з більшим versionCode встановиться
   поверх поточного, без видалення та зі збереженням даних.

УВАГА: Це оновлення ПІДПИСУ APK та встановлення поверх наявного додатка,
а не повністю автоматичне завантаження APK без участі користувача.
