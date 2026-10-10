"""اختبارات تهيئة قاعدة الإقلاع التلقائية (bootstrap): إنشاء الجداول
والمسؤول الأول من إعدادات التطبيق. تعمل بقاعدة SQLite في الذاكرة تماماً."""
from __future__ import annotations

from sqlalchemy import inspect

from app import _bootstrap_database, create_app
from app.extensions import db
from app.models import Role, User


def _make_app() -> object:
    """تطبيق بقاعدة SQLite في الذاكرة، مع إيقاف شرط الاختبار كي يعمل bootstrap."""
    app = create_app("test")
    app.config["TESTING"] = False
    return app


def test_bootstrap_creates_tables_and_admin():
    app = _make_app()
    app.config["ADMIN_USERNAME"] = "admin"
    app.config["ADMIN_PASSWORD"] = "Strong-pass-!9"
    app.config["ADMIN_DISPLAY_NAME"] = "مدير النظام"

    _bootstrap_database(app)
    with app.app_context():
        admin = db.session.scalar(db.select(User).where(User.username == "admin"))
        assert admin is not None
        assert admin.role is Role.ADMIN
        assert admin.display_name == "مدير النظام"
        assert admin.check_password("Strong-pass-!9")

    # إعادة الإقلاع (استدعاء ثانٍ) لا تنشئ مسؤولاً مكرراً
    _bootstrap_database(app)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(User.id))) == 1

    # تغيير ADMIN_PASSWORD ثم الإقلاع يزامن كلمة مرور المسؤول
    app.config["ADMIN_PASSWORD"] = "Another-pass-!7"
    _bootstrap_database(app)
    with app.app_context():
        admin = db.session.scalar(db.select(User).where(User.username == "admin"))
        assert admin.check_password("Another-pass-!7")


def test_bootstrap_creates_tables_even_without_admin():
    app = _make_app()  # ADMIN_USERNAME/ADMIN_PASSWORD فارغة

    _bootstrap_database(app)
    with app.app_context():
        assert "user" in inspect(db.engine).get_table_names()
        assert db.session.scalar(db.select(db.func.count(User.id))) == 0


def test_bootstrap_skips_in_testing_mode():
    app = create_app("test")  # TESTING مفعلة => لا شيء

    _bootstrap_database(app)
    with app.app_context():
        assert "user" not in inspect(db.engine).get_table_names()