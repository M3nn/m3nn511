"""اختبارات المخطط والنماذج — التحقق من القيود وسلوك slugify."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    Article,
    ArticleStatus,
    Category,
    Priority,
    Role,
    Task,
    TaskStatus,
    User,
    slugify,
)


def test_slugify_arabic_and_latin():
    assert slugify("النصر يفوز على الهلال") == "النصر-يفوز-على-الهلال"
    assert slugify("  Hello   World  ") == "hello-world"
    assert slugify("مباراة 2024/2025") == "مباراة-2024-2025"
    assert slugify("") == "item"
    assert slugify("!!!") == "item"


def test_slug_is_unique_per_article(app, article, users, category):
    second = Article(
        title=article.title,  # نفس العنوان عمداً
        body="متن بديل طويل بما يكفي لاجتياز الحد الأدنى للأحرف المطلوبة هنا.",
        status=ArticleStatus.DRAFT,
        category_id=category.id,
        author_id=users["editor"].id,
    )
    second.regenerate_slug()
    db.session.add(second)
    db.session.commit()
    assert second.slug != article.slug
    assert second.slug.endswith("-2")


def test_username_is_unique(app, users):
    db.session.add(
        User(username="editor", display_name="مكرر", role=Role.WRITER, password_hash="x")
    )
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_status_labels_are_arabic(app, users, category):
    art = Article(title="عنوان صالح تماماً للاختبار", body="متن" * 50,
                  status=ArticleStatus.PUBLISHED, category_id=category.id)
    assert art.status is ArticleStatus.PUBLISHED
    assert art.status_label == "منشور"
    art.status = ArticleStatus.DRAFT
    assert art.status_label == "مسودة"


def test_task_advance_walks_through_states(task):
    assert task.status is TaskStatus.TODO
    assert task.next_status() is TaskStatus.DOING
    assert task.advance() is True
    assert task.status is TaskStatus.DOING
    assert task.advance() is True
    assert task.status is TaskStatus.DONE
    assert task.next_status() is None
    assert task.advance() is False


def test_task_overdue_flag(task):
    today = dt.date.today()
    task.due_date = today - dt.timedelta(days=2)
    assert task.is_overdue is True
    task.status = TaskStatus.DONE
    assert task.is_overdue is False
    task.status = TaskStatus.TODO
    task.due_date = today + dt.timedelta(days=2)
    assert task.is_overdue is False


def test_article_body_paragraphs(article):
    paragraphs = article.body_paragraphs
    assert len(paragraphs) == 4
    assert all(p.strip() for p in paragraphs)


def test_role_capabilities(users):
    assert users["admin"].can_edit_articles is True
    assert users["editor"].can_edit_articles is True
    assert users["writer"].can_edit_articles is False
    assert users["admin"].is_admin is True
    assert users["writer"].is_admin is False


def test_password_hash_is_not_plaintext(users):
    user = users["editor"]
    assert "editor123" not in user.password_hash
    assert user.check_password("editor123") is True
    assert user.check_password("wrong-pass") is False


def test_category_relationship(article, category):
    assert article.category is category
    assert article in category.articles


def test_task_defaults(app, users):
    t = Task(title="مهمة بالحقول الافتراضية", assignee_id=users["admin"].id)
    db.session.add(t)
    db.session.commit()
    assert t.status is TaskStatus.TODO
    assert t.priority is Priority.MED
    assert t.article_id is None


def test_repr_does_not_leak_secrets(users):
    assert "editor123" not in repr(users["editor"])
    assert "editor" in repr(users["editor"])
