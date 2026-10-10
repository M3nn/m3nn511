# قواعد ProGuard/R8 لمشروع أخبار النصر
# WebView يستدعي JavaScript عبر الواجهة، لذا لا حاجة لقواعد خاصة حاليًا.
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
