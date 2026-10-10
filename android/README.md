# 📱 تطبيق أندرويد — منصة أخبار النصر

تطبيق أصلي (Kotlin) يغلّف منصة الويب ويعرضها كتطبيق كامل على الجوال.

## المزايا
- تصفّح الموقع داخل التطبيق (WebView أصلي).
- **سحب للتحديث** (Pull to refresh).
- **زر رجوع ذكي**: يتنقّل داخل الموقع ثم يخرج.
- **رفع الصور** في لوحة التحرير (مُحدّد ملفات أصلي).
- فتح الروابط الخارجية (واتساب، البريد، الهاتف، يوتيوب…) في المتصفح.
- شاشة **«تعذّر الاتصال»** مع زر إعادة المحاولة عند انقطاع الشبكة.
- أيقونة تكيّفية (Adaptive icon) بشعار النادي + شاشة إقلاع.
- دعم فتح روابط الموقع داخل التطبيق (Deep links / App Links).

## المسار المتوقّع
```
android/nassr-news/
├── app/src/main/java/com/nassr/news/MainActivity.kt   ← منطق التطبيق
├── app/src/main/res/                                   ← الأيقونات والتصميم
├── app/build.gradle.kts
└── build-apk.bat                                       ← بناء سريع على ويندوز
```

## الطريقة 1 — Android Studio (الأسهل والموصى بها)
1. نزّل **Android Studio**: <https://developer.android.com/studio>
2. `File ▸ Open` ثم اختر المجلد: `android/nassr-news`
3. انتظر مزامنة Gradle (تنزّل المكوّنات تلقائيًا).
4. اضغط **Run ▶** لتشغيله على محاكي أو جوال حقيقي.
5. للإصدار النهائي: `Build ▸ Generate Signed Bundle / APK`.

## الطريقة 2 — سطر الأوامر (Windows)
المتطلبات: **JDK 17** + **Android SDK** (مع ضبط `ANDROID_HOME`).
```bat
cd android\nassr-news
build-apk.bat
```
الناتج: `app\build\outputs\apk\debug\app-debug.apk`

لتثبيته على جوال موصول بكابل USB (مع تفعيل USB debugging):
```bat
gradlew.bat installDebug
```

## تغيير رابط الموقع
كل الروابط في مكان واحد داخل `MainActivity.kt`:
```kotlin
const val BASE_URL = "https://nassr-news.onrender.com"
private const val HOST = "nassr-news.onrender.com"
```
غيّر القيمتين إن نقلت الموقع إلى نطاق آخر.

## ملاحظات
- التطبيق يعمل مع **PWA** الموجود في الموقع (نفس الهوية والأيقونات).
- `App Links` (`autoVerify`) يعمل بالكامل فقط بعد استضافة ملف
  `.well-known/assetlinks.json` على الموقع. بدونه يعمل التطبيق عاديًا،
  لكن فتح روابط الموقع من خارج التطبيق قد يعرض نافذة اختيار.
- للإصدار على Google Play تحتاج **keystore** للتوقيع + حساب مطوّر.
