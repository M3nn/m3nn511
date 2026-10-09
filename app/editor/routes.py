"""لوحة التحرير: إدارة المقالات + AI-1 (تلخيص خبر).

الصلاحيات: محرّر ومدير فقط. كاتب يصل هنا يحصل على 403 من unauthorized_handler.
"""
from __future__ import annotations

import logging

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.ai import service as ai
from app.core.pagination import page_arg, paginate
from app.editor.forms import ArticleForm
from app.extensions import db
from app.models import Article, ArticleStatus, Category, Task, TaskStatus, utcnow

log = logging.getLogger("app.editor")

bp = Blueprint("editor", __name__)


def _require_editor():
    if not current_user.can_edit_articles:
        abort(403)


def _category_choices() -> list[tuple[int, str]]:
    return [(0, "— بدون تصنيف —")] + [
        (c.id, c.name)
        for c in db.session.scalars(select(Category).order_by(Category.name)).all()
    ]


def _get_article_or_404(article_id: int) -> Article:
    art = db.session.get(Article, article_id)
    if art is None:
        abort(404)
    return art


def _linked_task_counts(article_ids: list[int]) -> dict[int, int]:
    """{article_id: عدد المهام المرتبطة} باستعلام واحد."""
    if not article_ids:
        return {}
    return dict(
        db.session.execute(
            select(Task.article_id, func.count(Task.id))
            .where(Task.article_id.in_(article_ids))
            .group_by(Task.article_id)
        ).all()
    )


def _wants_task_delete() -> bool:
    """خيار «احذف المهام المرتبطة أيضاً» — إداري فقط؛ غيره يُتجاهَل طلبه."""
    return bool(current_user.is_admin) and request.form.get("delete_tasks") == "1"


@bp.before_request
@login_required
def _guard():
    _require_editor()


@bp.route("", methods=["GET"])
@bp.route("/", methods=["GET"])
def index():
    status_filter = request.args.get("status") or ""
    stmt = select(Article)
    if status_filter in {s.value for s in ArticleStatus}:
        stmt = stmt.where(Article.status == ArticleStatus(status_filter))
    stmt = stmt.order_by(Article.updated_at.desc(), Article.id.desc())

    per_page = current_app.config["ITEMS_PER_PAGE_ADMIN"]
    page = paginate(db.session, stmt, per_page, page=page_arg())
    counts = {
        row[0].value: row[1]
        for row in db.session.execute(
            select(Article.status, func.count(Article.id)).group_by(Article.status)
        ).all()
    }
    log.info("editor.index page=%s total=%s filter=%r", page.page, page.total, status_filter)
    return render_template(
        "editor/list.html", page=page, counts=counts, status_filter=status_filter
    )


@bp.route("/articles/new", methods=["GET", "POST"])
def new():
    form = ArticleForm()
    form.category_id.choices = _category_choices()
    if form.validate_on_submit():
        art = Article(
            title=form.title.data,
            body=form.body.data,
            summary=(form.summary.data or "").strip() or None,
            cover_image_url=(form.cover_image_url.data or "").strip() or None,
            status=ArticleStatus(form.status.data),
            category_id=form.category_id.data or None,
            author_id=current_user.id,
        )
        if art.is_published and art.published_at is None:
            art.published_at = utcnow()
        art.regenerate_slug()
        db.session.add(art)
        db.session.commit()
        log.info("editor.article_created id=%s by=%s status=%s",
                 art.id, current_user.username, art.status.value)
        flash("تم حفظ المقال بنجاح.", "success")
        return redirect(url_for("editor.edit", article_id=art.id))
    return render_template("editor/form.html", form=form, article=None)


@bp.route("/articles/<int:article_id>/edit", methods=["GET", "POST"])
def edit(article_id: int):
    art = _get_article_or_404(article_id)
    # العنوان المخزَّن قبل تطبيق النموذج — نحتاجه لقرار إعادة توليد الـ slug
    stored_title = art.title
    form = ArticleForm(obj=art)
    form.category_id.choices = _category_choices()

    if form.validate_on_submit():
        art.title = form.title.data
        art.body = form.body.data
        art.summary = (form.summary.data or "").strip() or None
        art.cover_image_url = (form.cover_image_url.data or "").strip() or None
        art.status = ArticleStatus(form.status.data)
        art.category_id = form.category_id.data or None
        if art.is_published and art.published_at is None:
            art.published_at = utcnow()
        if art.title != stored_title:
            art.regenerate_slug()
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            log.error("editor.article_conflict id=%s", art.id)
            flash("تعذّر الحفظ: العنوان يتعارض مع خبر آخر.", "error")
            return render_template("editor/form.html", form=form, article=art), 409
        log.info("editor.article_updated id=%s by=%s", art.id, current_user.username)
        flash("تم تحديث المقال.", "success")
        return redirect(url_for("editor.edit", article_id=art.id))

    return render_template("editor/form.html", form=form, article=art)


@bp.route("/articles/<int:article_id>/publish", methods=["POST"])
def publish(article_id: int):
    art = _get_article_or_404(article_id)
    if art.is_published:
        art.status = ArticleStatus.DRAFT
        art.published_at = None
        message = "أُعيد المقال إلى المسودات."
    else:
        if len((art.body or "").strip()) < 80:
            log.warning("editor.publish_rejected id=%s reason=short_body", art.id)
            flash("لا يمكن نشر خبر متنه أقصر من 80 حرفاً.", "error")
            return redirect(url_for("editor.edit", article_id=art.id))
        art.status = ArticleStatus.PUBLISHED
        art.published_at = utcnow()
        message = "تم نشر الخبر وهو الآن ظاهر للزوار."
    db.session.commit()
    log.info("editor.publish_toggled id=%s status=%s by=%s",
             art.id, art.status.value, current_user.username)
    flash(message, "success")
    return redirect(url_for("editor.edit", article_id=art.id))


@bp.route("/articles/<int:article_id>/delete", methods=["POST"])
def delete(article_id: int):
    art = _get_article_or_404(article_id)
    linked_tasks = _linked_task_counts([art.id]).get(art.id, 0)
    force = _wants_task_delete()
    if linked_tasks and not force:
        log.warning("editor.delete_blocked id=%s tasks=%s", art.id, linked_tasks)
        flash(f"لا يمكن حذف الخبر: مرتبط بـ {linked_tasks} مهمة. ألغِ الربط أولاً.", "error")
        return redirect(url_for("editor.edit", article_id=art.id))

    title = art.title
    if force:
        for task in list(art.tasks):
            db.session.delete(task)
    db.session.delete(art)
    db.session.commit()
    if force and linked_tasks:
        log.info("editor.article_deleted_with_tasks id=%s tasks=%s by=%s",
                 art.id, linked_tasks, current_user.username)
        flash(
            "تم حذف الخبر و"
            f"{_count_ar(linked_tasks, 'مهمة واحدة', 'مهمتين', 'مهام', 'مهمة')} مرتبطة به نهائياً.",
            "info",
        )
    else:
        log.info("editor.article_deleted id=%s title=%r by=%s", art.id, title, current_user.username)
        flash("تم حذف الخبر نهائياً.", "info")
    return redirect(url_for("editor.index"))


def _count_ar(n: int, one: str, two: str, few: str, many: str) -> str:
    """عدّد عربي: مفرد، مثنى، جمع القِلّة (3-10)، جمع الكثرة."""
    if n == 1:
        return one
    if n == 2:
        return two
    if 3 <= n <= 10:
        return f"{n} {few}"
    return f"{n} {many}"


def _back_to_index():
    """يعيد إلى قائمة التحرير مع الحفاظ على الفلتر ورقم الصفحة."""
    args: dict = {}
    status = request.form.get("status") or ""
    if status in {s.value for s in ArticleStatus}:
        args["status"] = status
    try:
        page = int(request.form.get("page") or 1)
    except ValueError:
        page = 1
    if page > 1:
        args["page"] = page
    return redirect(url_for("editor.index", **args))


@bp.route("/articles/delete-selected", methods=["POST"])
def delete_selected():
    """الحذف الجماعي: يحذف المقالات المختارة، والمرتبطة بمهام يقرّرها المدير.

    الافتراضي (كل الأدوار): مقال مرتبط بمهام لا يُحذف ويُبلَّغ عنه.
    استثناء إداري: مربّع «احذف المهام المرتبطة أيضاً» يحذف المهام مع المقال.
    """
    selected: list[int] = []
    for raw in request.form.getlist("ids"):
        try:
            selected.append(int(raw))
        except ValueError:
            log.warning("editor.delete_selected_bad_id %r", raw)
    # إزالة التكرار مع حفاظ ترتيب اختيار المستخدم
    selected = list(dict.fromkeys(selected))

    if not selected:
        flash("لم تختر أي مقالة للحذف.", "error")
        return _back_to_index()

    articles = db.session.scalars(
        select(Article).where(Article.id.in_(selected)).order_by(Article.id)
    ).all()
    if not articles:
        flash("المقالات المحدّدة لم تعد موجودة.", "error")
        return _back_to_index()

    # استعلام واحد لكل المقالات المحددة قبل أي حذف (لا حذف متقطّع داخل حلقة)
    linked_counts = _linked_task_counts([a.id for a in articles])
    force = _wants_task_delete()

    deleted = 0
    deleted_tasks = 0
    blocked: list[tuple[str, int]] = []
    for art in articles:
        linked = linked_counts.get(art.id, 0)
        if linked and not force:
            blocked.append((art.title, linked))
            continue
        if linked:  # force=True هنا حتماً: المدير طلب حذف المهام المرتبطة
            for task in list(art.tasks):
                db.session.delete(task)
            deleted_tasks += linked
        db.session.delete(art)
        deleted += 1
    if deleted:
        db.session.commit()

    if deleted:
        log.info(
            "editor.articles_deleted count=%s tasks=%s ids=%s by=%s",
            deleted, deleted_tasks, selected, current_user.username,
        )
        message = f"تم حذف {_count_ar(deleted, 'مقالة واحدة', 'مقالتين', 'مقالات', 'مقالة')}"
        if deleted_tasks:
            message += (
                " و"
                + _count_ar(deleted_tasks, 'مهمة واحدة', 'مهمتين', 'مهام', 'مهمة')
                + " مرتبطة بها"
            )
        flash(message + ".", "info")
    if blocked:
        total_tasks = sum(n for _, n in blocked)
        names = "، ".join(f"«{title}»" for title, _ in blocked[:3])
        rest = len(blocked) - 3
        more = f" {_count_ar(rest, 'وأخرى واحدة', 'وأخرى اثنتين', 'وأخرى', 'وأخرى')}" if rest else ""
        log.warning(
            "editor.delete_selected_blocked count=%s tasks=%s by=%s",
            len(blocked), total_tasks, current_user.username,
        )
        flash(
            "تعذّر حذف "
            f"{_count_ar(len(blocked), 'مقالة واحدة مرتبطة', 'مقالتين مرتبطتين', 'مقالات مرتبطة', 'مقالة مرتبطة')}"
            f" بـ {_count_ar(total_tasks, 'مهمة واحدة', 'مهمتين', 'مهام', 'مهمة')}: {names}{more}."
            " ألغِ الربط أولاً.",
            "error",
        )
    return _back_to_index()


# ============ AI-1: تلخيص الخبر ============

@bp.route("/articles/<int:article_id>/ai-summary", methods=["POST"])
def ai_summary(article_id: int):
    """HTMX: يستبدل صندوق الملخص بالنتيجة أو برسالة الخطأ العربية."""
    art = _get_article_or_404(article_id)
    try:
        result = ai.summarize(art.body)
    except ai.AIFailure as exc:
        log.warning("editor.ai_summary_failed id=%s status=%s", art.id, exc.status)
        if request.headers.get("HX-Request"):
            return render_template(
                "partials/ai_summary.html", article=art, error=exc.message
            ), 200 if exc.status == 400 else 503
        flash(exc.message, "error")
        return redirect(url_for("editor.edit", article_id=art.id))

    art.summary = result.data
    db.session.commit()
    log.info("editor.ai_summary_ok id=%s tokens=%s lat_ms=%s",
             art.id, result.input_tokens + result.output_tokens, result.lat_ms)
    return render_template("partials/ai_summary.html", article=art, error=None)


# ============ إحصاء بسيط للوحة ============

@bp.route("/stats", methods=["GET"])
def stats():
    """ملخّص تشغيلي: عدّ المقالات والمهام النشطة."""
    articles = {
        row[0].value: row[1]
        for row in db.session.execute(
            select(Article.status, func.count(Article.id)).group_by(Article.status)
        ).all()
    }
    tasks = {
        row[0].value: row[1]
        for row in db.session.execute(
            select(Task.status, func.count(Task.id)).group_by(Task.status)
        ).all()
    }
    return render_template(
        "editor/stats.html", articles=articles, tasks=tasks,
        active_tasks=tasks.get(TaskStatus.TODO.value, 0) + tasks.get(TaskStatus.DOING.value, 0),
    )
