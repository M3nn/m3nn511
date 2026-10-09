"""ملف WSGI لتطبيقات Python لدى الاستضافات التي تستخدم ``Passenger`` (cPanel…).

يستورد التطبيق البنّاء الجاهز من ``run.py`` بلا أي تشغيل للخادم (حارس الـ
``__main__`` يمنع تنفيذ ``main()`` عند الاستيراد).

بالنسبة للوحات cPanel التي تنشئ هذا الملف تلقائياً يكفي تحديد:
    Application startup file = run.py
    Application entry point  = app
"""
from run import app as application

__all__ = ["application"]