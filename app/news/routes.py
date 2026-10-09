"""الموقع العام: الرئيسية، التصنيفات، صفحة الخبر، البحث. قراءة فقط بلا مصادقة."""
from __future__ import annotations

import logging

from flask import Blueprint, abort, current_app, render_template, request
from sqlalchemy import or_, select

from app.core.pagination import page_arg, paginate
from app.extensions import db
from app.league.service import get_league
from app.models import Article, ArticleStatus, Category

log = logging.getLogger("app.news")

bp = Blueprint("news", __name__)

def _page_size() -> int:
    """حجم صفحة الموقع العام من الإعدادات، فقيمة واحدة لكل News route."""
    return int(current_app.config["ITEMS_PER_PAGE"])


def _wants_partial() -> bool:
    """طلب «شاهد المزيد» عبر HTMX: يُرجع البطاقات فقط بدل الصفحة كاملة."""
    return request.args.get("partial") == "1"


def _published_stmt():
    """الاستعلام الأساسي: المنشور فقط، الأحدث أولاً."""
    return (
        select(Article)
        .where(Article.status == ArticleStatus.PUBLISHED)
        .order_by(Article.published_at.desc().nulls_last(), Article.id.desc())
    )


def _get_published(slug: str) -> Article:
    article = db.session.scalar(_published_stmt().where(Article.slug == slug))
    if article is None:
        abort(404)
    return article


@bp.route("/", methods=["GET"])
def home():
    page = paginate(db.session, _published_stmt(), _page_size(), page=page_arg())
    hero = page.items[0] if page.items else None
    # الأول خبر رئيسي بعرض كامل، والباقي شبكة بطاقات متساوية
    grid = page.items[1:] if page.items else []

    # دفعة «شاهد المزيد»: كل عناصر الصفحة شبكة، بلا Hero
    if _wants_partial():
        log.info("news.home.partial page=%s items=%s", page.page, len(page.items))
        return render_template(
            "news/_more.html",
            page=page, items=page.items, endpoint="news.home", extra={},
        )

    categories = db.session.scalars(
        select(Category).order_by(Category.sort_order, Category.name)
    ).all()
    # عدّ المقالات المنشورة لكل تصنيف
    counts = dict(
        db.session.execute(
            select(Article.category_id, db.func.count(Article.id))
            .where(Article.status == ArticleStatus.PUBLISHED)
            .group_by(Article.category_id)
        ).all()
    )

    log.info("news.home page=%s items=%s total=%s", page.page, len(page.items), page.total)
    return render_template(
        "news/home.html",
        page=page, hero=hero, grid=grid,
        categories=categories, counts=counts,
        league=get_league(),
    )


@bp.route("/category/<slug>", methods=["GET"])
def category(slug: str):
    category_obj = db.session.scalar(select(Category).where(Category.slug == slug))
    if category_obj is None:
        abort(404)
    stmt = _published_stmt().where(Article.category_id == category_obj.id)
    page = paginate(db.session, stmt, _page_size())
    log.info("news.category slug=%s page=%s total=%s", slug, page.page, page.total)
    if _wants_partial():
        return render_template(
            "news/_more.html",
            page=page, items=page.items, endpoint="news.category", extra={"slug": slug},
        )
    return render_template("news/category.html", page=page, category=category_obj)


@bp.route("/article/<slug>", methods=["GET"])
def article(slug: str):
    art = _get_published(slug)
    # أخبار ذات صلة: نفس التصنيف، عدّا هذا الخبر، أحدث 3
    related: list[Article] = []
    if art.category_id:
        related = list(
            db.session.scalars(
                _published_stmt()
                .where(Article.category_id == art.category_id, Article.id != art.id)
                .limit(3)
            ).all()
        )
    log.info("news.article slug=%s id=%s", slug, art.id)
    return render_template("news/article.html", article=art, related=related)


@bp.route("/search", methods=["GET"])
def search():
    query = (request.args.get("q") or "").strip()
    stmt = _published_stmt()
    if query:
        pattern = f"%{query}%"
        stmt = stmt.where(or_(Article.title.ilike(pattern), Article.body.ilike(pattern)))
    page = paginate(db.session, stmt, _page_size())
    log.info("news.search q=%r page=%s total=%s", query, page.page, page.total)
    if _wants_partial():
        return render_template(
            "news/_more.html",
            page=page, items=page.items, endpoint="news.search", extra={"q": query},
        )
    return render_template("news/search.html", page=page, query=query)
