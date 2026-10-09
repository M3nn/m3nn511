"""أدوات مشتركة تُستدعى فعلياً من أكثر من موضع (5 استدعاءات)."""
from __future__ import annotations

from dataclasses import dataclass

from flask import request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.extensions import db


@dataclass
class Page:
    """نتيجة صفح واحد جاهزة للعرض في القوالب."""

    items: list
    page: int
    pages: int
    total: int
    has_prev: bool
    has_next: bool
    prev_num: int | None
    next_num: int | None

    @property
    def numbers(self) -> list[int]:
        """نافذة أرقام مختصرة حول الصفحة الحالية (حدودها 7 عناصر)."""
        if self.pages <= 7:
            return list(range(1, self.pages + 1))
        start = max(1, min(self.page - 2, self.pages - 6))
        return list(range(start, start + 7))


def page_arg() -> int:
    """يقرأ ?page= بأمان؛ أي قيمة غير صالحة تسقط إلى 1."""
    try:
        value = int(request.args.get("page", 1))
    except (TypeError, ValueError):
        return 1
    return value if value >= 1 else 1


def paginate(
    session: Session, stmt, per_page: int, page: int | None = None
) -> Page:
    """يعدّ النتائج وينفّذ الاستعلام بصفحة واحدة فقط."""
    page = page_arg() if page is None else max(1, page)
    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    pages = max(1, -(-total // per_page))  # تقريب لأعلى
    page = min(page, pages)
    items = list(session.scalars(stmt.limit(per_page).offset((page - 1) * per_page)).all())
    return Page(
        items=items,
        page=page,
        pages=pages,
        total=total,
        has_prev=page > 1,
        has_next=page < pages,
        prev_num=page - 1 if page > 1 else None,
        next_num=page + 1 if page < pages else None,
    )
