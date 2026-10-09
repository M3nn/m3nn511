@echo off
REM تشغيل خادم منصة النصر (Flask/waitress) على المنفذ 8000.
REM يجب أن يعمل هذا الخادم حتى يستطيع أباتشي (XAMPP) تمرير الطلبات إليه.
cd /d "%~dp0"
echo.
echo   تشغيل خادم منصة النصر على http://127.0.0.1:8000
echo   الموقع عبر XAMPP: http://nassr.test
echo   للإيقاف اضغط Ctrl+C
echo.
".venv\Scripts\python.exe" run.py
pause
