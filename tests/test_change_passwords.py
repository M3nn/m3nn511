"""اختبار أداة تغيير كلمات المرور (change_passwords.py): الوظيفة الأساسية
تُختبر بلا نداء شبكة وبقاعدة بيانات SQLite في الذاكرة."""
from __future__ import annotations

import change_passwords

from app import create_app
from app.extensions import db
from app.models import Role, User


def _app_with_admin():
    app = create_app("test")
    with app.app_context():
        db.create_all()
        admin = User(username="admin", display_name="مدير النظام", role=Role.ADMIN)
        admin.set_password("old-password-1")
        db.session.add(admin)
        db.session.commit()
    return app


def _fetch(app, username: str):
    with app.app_context():
        return db.session.scalar(db.select(User).where(User.username == username))


def test_change_updates_an_existing_user_password():
    app = _app_with_admin()

    assert change_passwords.change(app, "admin", "new-password-2") is True

    user = _fetch(app, "admin")
    assert user.check_password("new-password-2")
    assert not user.check_password("old-password-1")


def test_change_creates_a_new_user_with_role():
    app = _app_with_admin()

    assert change_passwords.change(
        app, "chief", "strong-pass-9", display="رئيس التحرير", role=Role.ADMIN
    ) is True

    user = _fetch(app, "chief")
    assert user is not None
    assert user.role is Role.ADMIN
    assert user.display_name == "رئيس التحرير"
    assert user.check_password("strong-pass-9")


def test_change_rejects_a_missing_user_without_role():
    app = _app_with_admin()

    assert change_passwords.change(app, "ghost", "some-pass-1") is False
    assert _fetch(app, "ghost") is None