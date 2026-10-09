"""كل نماذج قاعدة البيانات في ملف واحد — قرار تجريبي موثّق في PROJECT_MAP.

التقسيم إلى news/models.py و tasks/models.py مع 5 نماذج وعلاقة Article↔Task
كان سيُنتج ملفات 12-سطر واستيرادات دائرية.
"""
from __future__ import annotations

import enum
import re
import unicodedata
from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import (
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


def utcnow() -> datetime:
    """UTC دائماً، ثم يُحوَّل للتوقيت المحلي عند العرض."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# كل النماذج ترث db.Model مباشرةً؛ هكذا تدخل جداولها في db.metadata
# التي يبني منها db.create_all() الجداول فعلاً.


_ARABIC_DIACRITICS = re.compile(r"[\u0617-\u061A\u064B-\u0652]")
_NON_SLUG = re.compile(r"[^a-z0-9\u0600-\u06FF]+")


def slugify(text: str) -> str:
    """يولّد slug من نص عربي أو لاتيني مع ضمان حدّ أطول."""
    text = _ARABIC_DIACRITICS.sub("", (text or "").strip().lower())
    text = unicodedata.normalize("NFKC", text)
    parts = [p for p in _NON_SLUG.split(text) if p]
    return "-".join(parts)[:80].strip("-") or "item"


def unique_slug(model, base: str, field: str = "slug") -> str:
    """يضمن تفرّد الـ slug بإلحاق رقمي تصاعدي."""
    slug = slugify(base)
    candidate, n = slug, 2
    while db.session.query(model).filter(getattr(model, field) == candidate).first():
        candidate = f"{slug}-{n}"
        n += 1
    return candidate


class Role(str, enum.Enum):
    ADMIN = "admin"
    EDITOR = "editor"
    WRITER = "writer"


class ArticleStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class TaskStatus(str, enum.Enum):
    TODO = "todo"
    DOING = "doing"
    DONE = "done"


class Priority(str, enum.Enum):
    LOW = "low"
    MED = "med"
    HIGH = "high"


# تسميات عربية للعرض — مكانها هنا لتفادي جداول ترجمة متفرقة في القوالب
ROLE_LABELS = {Role.ADMIN: "مدير", Role.EDITOR: "محرر", Role.WRITER: "كاتب"}
ARTICLE_STATUS_LABELS = {
    ArticleStatus.DRAFT: "مسودة",
    ArticleStatus.PUBLISHED: "منشور",
}
TASK_STATUS_LABELS = {
    TaskStatus.TODO: "جديدة",
    TaskStatus.DOING: "قيد التنفيذ",
    TaskStatus.DONE: "منجزة",
}
PRIORITY_LABELS = {Priority.LOW: "منخفضة", Priority.MED: "متوسطة", Priority.HIGH: "عالية"}


class User(UserMixin, db.Model):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[Role] = mapped_column(
        SAEnum(Role, native_enum=False, length=10), default=Role.WRITER
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    articles: Mapped[list["Article"]] = relationship(back_populates="author")
    tasks: Mapped[list["Task"]] = relationship(back_populates="assignee")

    @property
    def is_active(self) -> bool:  # type: ignore[override]
        return True

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN

    @property
    def can_edit_articles(self) -> bool:
        """المحرّر والمدير يديران المقالات؛ الكاتب لا يملك ذلك."""
        return self.role in (Role.ADMIN, Role.EDITOR)

    @property
    def role_label(self) -> str:
        return ROLE_LABELS.get(self.role, self.role.value)

    def set_password(self, raw: str) -> None:
        from werkzeug.security import generate_password_hash

        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw: str) -> bool:
        from werkzeug.security import check_password_hash

        return check_password_hash(self.password_hash, raw)

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.role.value})>"


class Category(db.Model):
    __tablename__ = "category"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    slug: Mapped[str] = mapped_column(String(90), unique=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    articles: Mapped[list["Article"]] = relationship(back_populates="category")

    def __repr__(self) -> str:
        return f"<Category {self.name}>"


class Article(db.Model):
    __tablename__ = "article"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(250), index=True)
    slug: Mapped[str] = mapped_column(String(280), unique=True, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text)
    cover_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[ArticleStatus] = mapped_column(
        SAEnum(ArticleStatus, native_enum=False, length=12), default=ArticleStatus.DRAFT
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("category.id"), nullable=True
    )
    author_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id"), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    category: Mapped["Category | None"] = relationship(back_populates="articles")
    author: Mapped["User | None"] = relationship(back_populates="articles")
    tasks: Mapped[list["Task"]] = relationship(back_populates="article")

    __table_args__ = (
        Index("ix_article_status_published", "status", "published_at"),
        Index("ix_article_category", "category_id"),
    )

    @property
    def is_published(self) -> bool:
        return self.status == ArticleStatus.PUBLISHED

    @property
    def status_label(self) -> str:
        return ARTICLE_STATUS_LABELS.get(self.status, self.status.value)

    @property
    def body_paragraphs(self) -> list[str]:
        """المتن مقسّماً لفقرات — يمنع تسرّب الفواصل إلى HTML."""
        return [p.strip() for p in self.body.split("\n\n") if p.strip()]

    def regenerate_slug(self) -> None:
        self.slug = unique_slug(Article, self.title)

    def __repr__(self) -> str:
        return f"<Article {self.id} {self.status.value}>"


class Task(db.Model):
    __tablename__ = "task"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(250))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus, native_enum=False, length=10), default=TaskStatus.TODO
    )
    priority: Mapped[Priority] = mapped_column(
        SAEnum(Priority, native_enum=False, length=8), default=Priority.MED
    )
    due_date: Mapped[object | None] = mapped_column(Date, nullable=True)
    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id"), nullable=True
    )
    article_id: Mapped[int | None] = mapped_column(
        ForeignKey("article.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )

    assignee: Mapped["User | None"] = relationship(back_populates="tasks")
    article: Mapped["Article | None"] = relationship(back_populates="tasks")

    __table_args__ = (
        Index("ix_task_status", "status"),
        Index("ix_task_assignee", "assignee_id"),
    )

    @property
    def status_label(self) -> str:
        return TASK_STATUS_LABELS.get(self.status, self.status.value)

    @property
    def priority_label(self) -> str:
        return PRIORITY_LABELS.get(self.priority, self.priority.value)

    @property
    def is_overdue(self) -> bool:
        from datetime import date

        return bool(self.due_date) and self.due_date < date.today() and self.status != TaskStatus.DONE

    def next_status(self) -> TaskStatus | None:
        """انتقال الحالة خطوةً: جديدة ← قيد التنفيذ ← منجزة ← لا شيء."""
        order = [TaskStatus.TODO, TaskStatus.DOING, TaskStatus.DONE]
        nxt = order[order.index(self.status) + 1 :]
        return nxt[0] if nxt else None

    def advance(self) -> bool:
        nxt = self.next_status()
        if nxt is None:
            return False
        self.status = nxt
        return True

    def __repr__(self) -> str:
        return f"<Task {self.id} {self.status.value}>"


class AIUsage(db.Model):
    """سجل استهلاك وتكلفة الذكاء الاصطناعي — بديل السجلات للمحاسبة."""

    __tablename__ = "ai_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("user.id"), nullable=True
    )
    feature: Mapped[str] = mapped_column(String(40), index=True)
    model: Mapped[str] = mapped_column(String(40))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    lat_ms: Mapped[int] = mapped_column(Integer, default=0)
    ok: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped["User | None"] = relationship()

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def __repr__(self) -> str:
        return f"<AIUsage {self.feature} {self.model} ok={self.ok}>"
