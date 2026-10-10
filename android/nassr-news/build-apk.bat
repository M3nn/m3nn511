@echo off
REM ============================================================
REM  بناء تطبيق أندرويد «أخبار النصر» (APK للتجربة/التوزيع)
REM  المتطلبات: JDK 17 + Android SDK (أو افتح المشروع في Android Studio)
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo   [1/2] بناء نسخة debug (للتجربة السريعة) ...
call gradlew.bat assembleDebug
if errorlevel 1 goto :error
echo.
echo   تم إنشاء:  app\build\outputs\apk\debug\app-debug.apk
echo.
goto :end

:error
echo.
echo   فشل البناء. تأكد من تثبيت JDK 17 و Android SDK،
echo   أو افتح مجلد android\nassr-news داخل Android Studio واضغط Run.
echo.

:end
pause
