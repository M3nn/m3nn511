"""تسجيل الدخول والخروج — الموظفون فقط، بلا تسجيل عام."""
from __future__ import annotations

import logging
from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.auth.forms import LoginForm
from app.extensions import db
from app.models import User

log = logging.getLogger("app.auth")

bp = Blueprint("auth", __name__)


def _safe_next(target: str | None) -> str | None:
    """يمنع إعادة التوجيه إلى موقع خارجي (open redirect)."""
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/"):
        return None
    # مسار مطلق داخل الموقع فقط: نرفض //example.com و /a\..\b
    if target.startswith("//") or "\\" in target:
        return None
    return target


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("news.home"))

    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.scalar(db.select(User).where(User.username == form.username.data))
        if user and user.check_password(form.password.data):
            login_user(user, remember=False)
            log.info("auth.login_ok user=%s role=%s", user.username, user.role.value)
            flash(f"أهلاً بك، {user.display_name}.", "success")
            return redirect(_safe_next(request.args.get("next")) or url_for("news.home"))

        log.warning("auth.login_failed user=%s", form.username.data)
        flash("اسم المستخدم أو كلمة المرور غير صحيحة.", "error")

    return render_template("auth/login.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    log.info("auth.logout user=%s", current_user.username)
    logout_user()
    flash("تم تسجيل الخروج بنجاح.", "info")
    return redirect(url_for("news.home"))
