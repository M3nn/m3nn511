"""مُنشئ التطبيق — نقطة الدخول الوحيدة لكل الأجزاء."""
from __future__ import annotations

import logging
from datetime import datetime

from flask import Flask, render_template, request
from flask_login import current_user

from app.config import Config, resolve_config
from app.core.logging_setup import configure_logging, get_logger
from app.extensions import csrf, db, login_manager

log = get_logger(__name__)

AR_MONTHS = [
    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
    "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
]
AR_DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]


def format_time_12(hour: int, minute: int) -> str:
    """وقت بنظام 12 ساعة بصيغة عربية: «9:05 ص» و«12:00 م»."""
    period = "ص" if hour < 12 else "م"
    return f"{hour % 12 or 12}:{minute:02d} {period}"


def format_datetime(value: datetime | None, with_time: bool = True) -> str:
    """تاريخ عربي مقروء. يُستدعى من القوالب عبر المرشّح |ar."""
    if value is None:
        return ""
    text = f"{value.day} {AR_MONTHS[value.month - 1]} {value.year}"
    return f"{text} - {format_time_12(value.hour, value.minute)}" if with_time else text


def format_date(value) -> str:
    if value is None:
        return ""
    return f"{value.day} {AR_MONTHS[value.month - 1]} {value.year}"


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(resolve_config(config_name) or Config)
    Config.init_app(app)

    configure_logging(app)
    log.info("app.start debug=%s", app.debug)

    _register_extensions(app)
    _register_blueprints(app)
    _register_template_helpers(app)
    _register_error_handlers(app)
    _register_cli(app)
    _register_login(app)

    @app.after_request
    def _security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    return app


def _register_extensions(app: Flask) -> None:
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)


def _register_login(app: Flask) -> None:
    from app.models import User  # استيراد متأخر لكسر الدورية مع login_manager

    @login_manager.user_loader
    def load_user(user_id: str):
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    @login_manager.unauthorized_handler
    def unauthorized():
        """زائر يُحوَّل لتسجيل الدخول؛ موظف بلا صلاحية يحصل على 403."""
        from flask import abort, flash, redirect, url_for

        if current_user.is_authenticated:
            abort(403)
        flash("الرجاء تسجيل الدخول للوصول إلى لوحة التحرير.", "warning")
        # request.full_path adds a trailing "?" always; strip it so the
        # login URL does not become /auth/login?next=/editor?
        return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))


def _register_blueprints(app: Flask) -> None:
    from app.admin.routes import bp as admin_bp
    from app.auth.routes import bp as auth_bp
    from app.editor.routes import bp as editor_bp
    from app.news.routes import bp as news_bp
    from app.tasks.routes import bp as tasks_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(news_bp)
    app.register_blueprint(tasks_bp, url_prefix="/tasks")
    app.register_blueprint(editor_bp, url_prefix="/editor")
    app.register_blueprint(admin_bp, url_prefix="/admin")


def _register_template_helpers(app: Flask) -> None:
    @app.template_filter("ar")
    def _ar(value, with_time: bool = True) -> str:
        return format_datetime(value, with_time)

    @app.template_filter("ar_date")
    def _ar_date(value) -> str:
        return format_date(value)

    @app.context_processor
    def _globals():
        """متغيّرات متاحة في كل القوالب بلا تمرير يدوي."""
        from app.ai.service import is_configured
        from app.models import (
            ARTICLE_STATUS_LABELS,
            PRIORITY_LABELS,
            TASK_STATUS_LABELS,
            ArticleStatus,
            TaskStatus,
        )

        return {
            "nav_categories": _nav_categories(),
            "today_label": AR_DAYS[datetime.now().weekday()],
            "ai_ready": is_configured(),
            "current_user": current_user,
            "ArticleStatus": ArticleStatus,
            "TaskStatus": TaskStatus,
            "ARTICLE_STATUS_LABELS": ARTICLE_STATUS_LABELS,
            "TASK_STATUS_LABELS": TASK_STATUS_LABELS,
            "PRIORITY_LABELS": PRIORITY_LABELS,
        }


def _nav_categories():
    from app.models import Category

    try:
        return db.session.scalars(
            db.select(Category).order_by(Category.sort_order, Category.name)
        ).all()
    except Exception:
        # قبل init-db: الصفحة تعمل لكن بلا شريط تصنيفات
        log.debug("nav.categories_unavailable", exc_info=True)
        return []


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(403)
    def forbidden(error):  # noqa: ANN001, ARG001
        log.warning("http.403 path=%s", request.path)
        return render_template(
            "errors/error.html",
            code=403,
            message="ليست لديك صلاحية الوصول إلى هذه الصفحة.",
        ), 403

    @app.errorhandler(404)
    def not_found(error):  # noqa: ANN001, ARG001
        log.info("http.404 path=%s", request.path)
        return render_template(
            "errors/error.html",
            code=404,
            message="الصفحة المطلوبة غير موجودة.",
        ), 404

    @app.errorhandler(500)
    def server_error(error):  # noqa: ANN001, ARG001
        log.exception("http.500 path=%s", request.path)
        return render_template(
            "errors/error.html",
            code=500,
            message="حدث خطأ في الخادم. تم تسجيل المشكلة وسيُراجعها الفريق.",
        ), 500


def _register_cli(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db() -> None:
        """ينشئ الجداول. آمن للتكرار."""
        from app.models import AIUsage, Article, Category, Task, User  # noqa: F401

        db.create_all()
        log.info("db.created")
        print("تم إنشاء الجداول بنجاح.")

    @app.cli.command("drop-db")
    def drop_db() -> None:
        """يحذف كل الجداول. للتطوير فقط."""
        from app.models import AIUsage, Article, Category, Task, User  # noqa: F401

        db.drop_all()
        log.warning("db.dropped_all")
        print("تم حذف جميع الجداول.")

    @app.cli.command("seed")
    def seed() -> None:
        """يبذر بيانات تجريبية: مستخدمون وتصنيفات وأخبار ومهام."""
        from app.seed import seed_all

        for line in seed_all():
            print(line)
        log.info("db.seeded")

    @app.cli.command("fetch-league")
    def fetch_league() -> None:
        """يجلب نتائج ومواعيد دوري روشن ويحدّث الكاش دون انتظار المهلة."""
        from app.league.service import refresh

        payload = refresh()
        if payload is None:
            print("تعذّر جلب بيانات الدوري. راجع السجل أو تحقّق من الاتصال.")
            return
        print(
            f"تم التحديث: {len(payload['results'])} نتيجة، "
            f"{len(payload['fixtures'])} مباراة قادمة."
        )
        print(f"آخر تحديث: {payload['updated']}")
