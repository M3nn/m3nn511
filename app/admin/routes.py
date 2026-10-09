"""لوحة الإدارة: تحكّم مطلق في التصنيفات (إضافة/تحرير/حذف).

الصلاحية: المدير فقط. غيره (محرّر/كاتب) يحصل على 403.
حذف التصنيف لا يحذف الأخبار — تُفكّ من التصنيف فقط (category_id = NULL).
"""
from __future__ import annotations

import logging

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.admin.forms import CategoryForm
from app.extensions import db
from app.models import Article, Category, slugify

log = logging.getLogger("app.admin")

bp = Blueprint("admin", __name__)


@bp.before_request
@login_required
def _guard():
    """لوحة الإدارة محجوزة للمدير."""
    if not current_user.is_admin:
        abort(403)


def _get_category_or_404(category_id: int) -> Category:
    cat = db.session.get(Category, category_id)
    if cat is None:
        abort(404)
    return cat


def _slug_for(name: str, *, exclude_id: int | None = None) -> str:
    """slug فريد مع تجاهل التصنيف الحالي عند التعديل (منع لاحقة -2 الزائفة)."""
    base = slugify(name)
    candidate, n = base, 2
    while True:
        stmt = select(Category).where(Category.slug == candidate)
        if exclude_id is not None:
            stmt = stmt.where(Category.id != exclude_id)
        if db.session.scalar(stmt) is None:
            return candidate
        candidate = f"{base}-{n}"
        n += 1


def _name_taken(name: str, *, exclude_id: int | None = None) -> bool:
    stmt = select(Category).where(func.lower(Category.name) == name.strip().lower())
    if exclude_id is not None:
        stmt = stmt.where(Category.id != exclude_id)
    return db.session.scalar(stmt) is not None


@bp.route("/categories", methods=["GET"])
def categories():
    cats = db.session.scalars(
        select(Category).order_by(Category.sort_order, Category.name)
    ).all()
    counts = dict(
        db.session.execute(
            select(Article.category_id, func.count(Article.id))
            .where(Article.category_id.is_not(None))
            .group_by(Article.category_id)
        ).all()
    )
    log.info("admin.categories total=%s", len(cats))
    return render_template("admin/categories.html", categories=cats, counts=counts)


@bp.route("/categories/new", methods=["GET", "POST"])
def category_new():
    form = CategoryForm()
    if form.validate_on_submit():
        name = form.name.data.strip()
        if _name_taken(name):
            flash("يوجد تصنيف بنفس الاسم.", "error")
        else:
            cat = Category(name=name, sort_order=form.sort_order.data or 0)
            cat.slug = _slug_for(name)
            db.session.add(cat)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                log.error("admin.category_conflict name=%r", name)
                flash("تعذّر الحفظ: الاسم أو الرابط مستخدم.", "error")
            else:
                log.info(
                    "admin.category_created id=%s name=%r by=%s",
                    cat.id, cat.name, current_user.username,
                )
                flash("تمت إضافة التصنيف.", "success")
                return redirect(url_for("admin.categories"))
    return render_template("admin/category_form.html", form=form, category=None)


@bp.route("/categories/<int:category_id>/edit", methods=["GET", "POST"])
def category_edit(category_id: int):
    cat = _get_category_or_404(category_id)
    form = CategoryForm(obj=cat)
    if form.validate_on_submit():
        name = form.name.data.strip()
        if _name_taken(name, exclude_id=cat.id):
            flash("يوجد تصنيف آخر بنفس الاسم.", "error")
        else:
            renamed = name != cat.name
            cat.name = name
            cat.sort_order = form.sort_order.data or 0
            if renamed:
                cat.slug = _slug_for(name, exclude_id=cat.id)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                log.error("admin.category_conflict id=%s name=%r", cat.id, name)
                flash("تعذّر الحفظ: الاسم أو الرابط مستخدم.", "error")
            else:
                log.info("admin.category_updated id=%s by=%s", cat.id, current_user.username)
                flash("تم تحديث التصنيف.", "success")
                return redirect(url_for("admin.categories"))
    return render_template("admin/category_form.html", form=form, category=cat)


@bp.route("/categories/<int:category_id>/delete", methods=["POST"])
def category_delete(category_id: int):
    cat = _get_category_or_404(category_id)
    name = cat.name
    unlinked = len(cat.articles)
    # الأخبار لا تُحذف: تُفكّ من التصنيف فقط
    for art in list(cat.articles):
        art.category_id = None
    db.session.delete(cat)
    db.session.commit()
    log.info(
        "admin.category_deleted id=%s name=%r articles_unlinked=%s by=%s",
        category_id, name, unlinked, current_user.username,
    )
    message = f"تم حذف التصنيف «{name}»."
    if unlinked:
        message += f" وأُزيل من {unlinked} خبر (بقيت الأخبار بلا تصنيف)."
    flash(message, "info")
    return redirect(url_for("admin.categories"))