"""إدارة المهام التحريرية + AI-2 (اقتراح مهام من نص حرّ).

الصلاحيات: كل الموظفين. الكاتب يرى مهامه فقط ويعدّل مهامه فقط.
"""
from __future__ import annotations

import logging

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    get_flashed_messages,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError

from app.ai import service as ai
from app.core.pagination import page_arg, paginate
from app.extensions import db
from app.models import Article, ArticleStatus, Priority, Task, TaskStatus, User
from app.tasks.forms import TaskForm

log = logging.getLogger("app.tasks")

bp = Blueprint("tasks", __name__)


# ---------- الصلاحيات على مستوى الصف ----------

def _visible(task: Task) -> bool:
    """المحرّر والمدير يرى الكل؛ الكاتب يرى ما كُلِّف به فقط."""
    if current_user.can_edit_articles:
        return True
    return task.assignee_id == current_user.id


def _get_task_or_404(task_id: int) -> Task:
    task = db.session.get(Task, task_id)
    if task is None or not _visible(task):
        # 404 بدل 403 حتى لا نكشف وجود مهام الآخرين
        abort(404)
    return task


def _safe_assignee(value: int | None) -> int | None:
    """الكاتب لا يكلّف أحداً غير نفسه، حتى لو زوّر النموذج."""
    if current_user.can_edit_articles:
        return value or None
    return current_user.id


def _assignee_choices() -> list[tuple[int, str]]:
    users = db.session.scalars(select(User).order_by(User.display_name)).all()
    return [(0, "— غير محدّد —")] + [
        (u.id, f"{u.display_name} ({u.role_label})") for u in users
    ]


def _article_choices() -> list[tuple[int, str]]:
    """المقالات المنشورة أو ما كتبه المحرّر الحالي — يمنع ربطاً بلا معنى."""
    stmt = select(Article).order_by(Article.published_at.desc().nulls_last())
    if current_user.can_edit_articles:
        stmt = stmt.where(
            or_(
                Article.status == ArticleStatus.PUBLISHED,
                Article.author_id == current_user.id,
            )
        )
    else:
        stmt = stmt.where(Article.author_id == current_user.id)
    articles = db.session.scalars(stmt.limit(100)).all()
    return [(0, "— بدون ربط —")] + [(a.id, f"#{a.id} — {a.title[:60]}") for a in articles]


@bp.before_request
@login_required
def _guard():
    """كل مسارات /tasks تتطلّب حساب موظف. guests يُحوَّلون إلى صفحة الدخول."""
    return None


# ---------- القائمة ----------

@bp.route("", methods=["GET"])
@bp.route("/", methods=["GET"])
def index():
    status_filter = (request.args.get("status") or "").strip()
    mine_only = request.args.get("mine") == "1"
    can_manage = current_user.can_edit_articles
    scoped = not can_manage or mine_only

    stmt = select(Task)
    if scoped:
        stmt = stmt.where(Task.assignee_id == current_user.id)
    if status_filter in {s.value for s in TaskStatus}:
        stmt = stmt.where(Task.status == TaskStatus(status_filter))
    # العاجلة أولاً، ثم الأقدم استحقاقاً، ثم غير المؤرّخة
    stmt = stmt.order_by(
        case(
            (Task.status == TaskStatus.TODO, 0),
            (Task.status == TaskStatus.DOING, 1),
            else_=2,
        ),
        Task.due_date.is_(None),
        Task.due_date,
        Task.id.desc(),
    )

    per_page = current_app.config["ITEMS_PER_PAGE_ADMIN"]
    page = paginate(db.session, stmt, per_page, page=page_arg())

    count_stmt = select(Task.status, func.count(Task.id)).group_by(Task.status)
    if scoped:
        count_stmt = count_stmt.where(Task.assignee_id == current_user.id)
    counts = {row[0].value: row[1] for row in db.session.execute(count_stmt).all()}

    log.info("tasks.index page=%s total=%s status=%r mine=%s",
             page.page, page.total, status_filter, mine_only)
    return render_template(
        "tasks/list.html",
        page=page,
        counts=counts,
        status_filter=status_filter,
        mine_only=mine_only,
        can_manage=can_manage,
    )


# ---------- إنشاء ----------

@bp.route("/new", methods=["GET", "POST"])
def new():
    """زر «أضف» بجانب كل اقتراح من AI يأتي بـ ?title=…&priority=…"""
    is_post = request.method == "POST"
    prefill_title = (request.form if is_post else request.args).get("title", "").strip()[:250]
    prefill_priority = (request.form if is_post else request.args).get("priority", "").strip()
    if prefill_priority not in {p.value for p in Priority}:
        prefill_priority = Priority.MED.value

    form = TaskForm()
    form.assignee_id.choices = _assignee_choices()
    form.article_id.choices = _article_choices()
    if not is_post and prefill_title:
        form.title.data = prefill_title
        form.priority.data = prefill_priority
        if not current_user.can_edit_articles:
            form.assignee_id.data = current_user.id

    if form.validate_on_submit():
        task = Task(
            title=form.title.data,
            description=(form.description.data or "").strip() or None,
            status=TaskStatus(form.status.data),
            priority=Priority(form.priority.data),
            due_date=form.due_date.data or None,
            assignee_id=_safe_assignee(form.assignee_id.data),
            article_id=form.article_id.data or None,
        )
        db.session.add(task)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            log.error("tasks.create_failed integrity")
            flash("تعذّر إنشاء المهمة. راجع البيانات وأعد المحاولة.", "error")
            return render_template("tasks/form.html", form=form, task=None), 409
        log.info("tasks.created id=%s by=%s assignee=%s",
                 task.id, current_user.username, task.assignee_id)
        flash("تم إنشاء المهمة.", "success")
        return redirect(url_for("tasks.index"))

    return render_template("tasks/form.html", form=form, task=None)


# ---------- تعديل ----------

@bp.route("/<int:task_id>/edit", methods=["GET", "POST"])
def edit(task_id: int):
    task = _get_task_or_404(task_id)
    can_manage = current_user.can_edit_articles

    form = TaskForm(obj=task)
    form.assignee_id.choices = _assignee_choices()
    form.article_id.choices = _article_choices()
    if not can_manage:
        form.assignee_id.data = current_user.id
        form.assignee_id.render_kw = {"disabled": True}

    if form.validate_on_submit():
        task.title = form.title.data
        task.description = (form.description.data or "").strip() or None
        task.status = TaskStatus(form.status.data)
        task.priority = Priority(form.priority.data)
        task.due_date = form.due_date.data or None
        task.assignee_id = _safe_assignee(form.assignee_id.data)
        task.article_id = form.article_id.data or None
        db.session.commit()
        log.info("tasks.updated id=%s by=%s", task.id, current_user.username)
        flash("تم تحديث المهمة.", "success")
        return redirect(url_for("tasks.index"))

    return render_template("tasks/form.html", form=form, task=task)


# ---------- تغيير الحالة ----------

@bp.route("/<int:task_id>/advance", methods=["POST"])
def advance(task_id: int):
    """ينقل الحالة خطوةً للأمام ويعيد الصف فقط (HTMX)."""
    task = _get_task_or_404(task_id)
    if task.advance():
        db.session.commit()
        log.info("tasks.advanced id=%s status=%s by=%s",
                 task.id, task.status.value, current_user.username)
    else:
        log.info("tasks.advance_noop id=%s status=%s", task.id, task.status.value)
    return render_template(
        "partials/task_row.html", task=task, standalone=True, oob_flash=True
    )


@bp.route("/<int:task_id>/status", methods=["POST"])
def set_status(task_id: int):
    """تعيين حالة صريحة من قائمة منسدلة — بديل بلا HTMX."""
    task = _get_task_or_404(task_id)
    wanted = (request.form.get("status") or "").strip()
    if wanted in {s.value for s in TaskStatus}:
        task.status = TaskStatus(wanted)
        db.session.commit()
        log.info("tasks.status_set id=%s status=%s by=%s",
                 task.id, wanted, current_user.username)
        flash("تم تحديث حالة المهمة.", "success")
    else:
        flash("قيمة حالة غير معروفة.", "error")
    return redirect(request.referrer or url_for("tasks.index"))


@bp.route("/<int:task_id>/delete", methods=["POST"])
def delete(task_id: int):
    task = _get_task_or_404(task_id)
    title = task.title
    db.session.delete(task)
    db.session.commit()
    log.info("tasks.deleted id=%s title=%r by=%s", task.id, title, current_user.username)
    flash("تم حذف المهمة.", "info")
    return redirect(url_for("tasks.index"))


# ---------- AI-2: اقتراح مهام من نص حرّ ----------

@bp.route("/suggest", methods=["GET", "POST"])
def suggest():
    """textarea + زر ⇒ HTMX يعيد قائمة عناوين مقترحة، لكل واحد زر «أضف»."""
    brief = (request.form.get("brief") or "").strip() if request.method == "POST" else ""
    suggestions: list[dict] = []
    error: str | None = None

    if request.method == "POST":
        try:
            suggestions = ai.suggest_tasks(brief).data
        except ai.AIFailure as exc:
            log.warning("tasks.ai_suggest_failed status=%s", exc.status)
            error = exc.message

    if request.headers.get("HX-Request"):
        return render_template(
            "partials/task_suggestions.html",
            suggestions=suggestions, error=error, brief=brief,
        )
    return render_template(
        "tasks/suggest.html", suggestions=suggestions, error=error, brief=brief
    )
