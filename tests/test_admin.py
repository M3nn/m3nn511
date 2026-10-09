"""اختبارات لوحة الإدارة: التحكم الكامل في التصنيفات (إضافة/تحرير/حذف) + الصلاحيات."""
from __future__ import annotations

from sqlalchemy import func, select

from app.extensions import db
from app.models import Category
from tests.conftest import login


def _category_count() -> int:
    return db.session.scalar(select(func.count(Category.id))) or 0


# ============ الصلاحيات: المدير فقط ============


def test_admin_categories_page_is_reachable_for_admin(client, users, category):
    login(client, "admin", "admin123")
    r = client.get("/admin/categories")
    assert r.status_code == 200
    assert category.name in r.get_data(as_text=True)


def test_editor_is_forbidden_from_categories(client, users):
    login(client, "editor", "editor123")
    assert client.get("/admin/categories").status_code == 403
    assert client.post("/admin/categories/new", data={"name": "تصنيف ممنوع"}).status_code == 403


def test_writer_is_forbidden_from_categories(client, users):
    login(client, "writer", "writer123")
    assert client.get("/admin/categories").status_code == 403


def test_anonymous_is_redirected_to_login(client, users):
    r = client.get("/admin/categories")
    assert r.status_code == 302
    assert "/auth/login" in r.headers["Location"]


def test_nav_shows_categories_link_to_admin_only(client, users):
    login(client, "admin", "admin123")
    assert "/admin/categories" in client.get("/").get_data(as_text=True)


def test_nav_hides_categories_link_from_editor(client, users):
    login(client, "editor", "editor123")
    assert "/admin/categories" not in client.get("/").get_data(as_text=True)


# ============ الإضافة ============


def test_admin_adds_a_category_with_generated_slug(client, users):
    login(client, "admin", "admin123")
    r = client.post(
        "/admin/categories/new",
        data={"name": "كرة الطائرة", "sort_order": "5"},
        follow_redirects=True,
    )
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "تمت إضافة التصنيف" in body

    cat = db.session.scalar(select(Category).where(Category.name == "كرة الطائرة"))
    assert cat is not None
    assert cat.sort_order == 5
    assert cat.slug, "يجب توليد رابط تلقائياً"
    assert " " not in cat.slug


def test_admin_cannot_add_duplicate_name(client, users, category):
    login(client, "admin", "admin123")
    before = _category_count()
    r = client.post(
        "/admin/categories/new",
        data={"name": category.name, "sort_order": "0"},
        follow_redirects=True,
    )
    assert "بنفس الاسم" in r.get_data(as_text=True)
    assert _category_count() == before


def test_blank_name_is_rejected(client, users):
    login(client, "admin", "admin123")
    before = _category_count()
    r = client.post("/admin/categories/new", data={"name": "", "sort_order": "0"})
    assert r.status_code == 200
    assert _category_count() == before


# ============ التحرير ============


def test_admin_renames_category_and_updates_slug(client, users, category):
    login(client, "admin", "admin123")
    old_slug = category.slug
    r = client.post(
        f"/admin/categories/{category.id}/edit",
        data={"name": "كرة القدم العالمية", "sort_order": "3"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "تم تحديث التصنيف" in r.get_data(as_text=True)
    db.session.refresh(category)
    assert category.name == "كرة القدم العالمية"
    assert category.sort_order == 3
    assert category.slug != old_slug


def test_edit_without_rename_keeps_slug(client, users, category):
    login(client, "admin", "admin123")
    slug = category.slug
    client.post(
        f"/admin/categories/{category.id}/edit",
        data={"name": category.name, "sort_order": "9"},
        follow_redirects=True,
    )
    db.session.refresh(category)
    assert category.slug == slug, "إعادة الحفظ بلا تغيير اسم لا تُنتج رابطاً مكرّراً بلاحقة"
    assert category.sort_order == 9


def test_rename_cannot_collide_with_another_category(client, users, category):
    login(client, "admin", "admin123")
    other = Category(name="كرة السلة", slug="كرة-السلة", sort_order=2)
    db.session.add(other)
    db.session.commit()

    r = client.post(
        f"/admin/categories/{other.id}/edit",
        data={"name": category.name, "sort_order": "0"},
        follow_redirects=True,
    )
    assert "بنفس الاسم" in r.get_data(as_text=True)
    db.session.refresh(other)
    assert other.name == "كرة السلة"


# ============ الحذف ============


def test_admin_deletes_category_and_keeps_its_articles(client, users, article, category):
    login(client, "admin", "admin123")
    r = client.post(f"/admin/categories/{category.id}/delete", follow_redirects=True)
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "تم حذف التصنيف" in body
    assert "بلا تصنيف" in body

    assert db.session.get(Category, category.id) is None
    db.session.refresh(article)
    assert article.category_id is None, "الخبر يبقى موجوداً بلا تصنيف"


def test_editor_cannot_delete_category(client, users, category):
    login(client, "editor", "editor123")
    r = client.post(f"/admin/categories/{category.id}/delete")
    assert r.status_code == 403
    assert db.session.get(Category, category.id) is not None