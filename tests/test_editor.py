"""اختبارات لوحة التحرير: إنشاء، تعديل، نشر، حذف، صلاحيات."""

from __future__ import annotations

from app.extensions import db
from app.models import Article, ArticleStatus, Task
from tests.conftest import login

VALID_BODY = "هذا متن طويل بما يكفي لاجتياز الحد الأدنى المطلوب للأحرف. " * 3


def test_editor_list_shows_articles(client, users, article):
    login(client, "editor", "editor123")
    r = client.get("/editor")
    assert r.status_code == 200
    assert article.title in r.get_data(as_text=True)


def test_editor_list_filters_by_status(client, users, article, draft):
    login(client, "editor", "editor123")
    body = client.get("/editor?status=published").get_data(as_text=True)
    assert article.title in body
    assert draft.title not in body

    body = client.get("/editor?status=draft").get_data(as_text=True)
    assert draft.title in body


def test_create_article(client, users, category):
    login(client, "editor", "editor123")
    r = client.post(
        "/editor/articles/new",
        data={
            "title": "عنوان خبر جديد مكتوب في الاختبار",
            "body": VALID_BODY,
            "status": "published",
            "category_id": str(category.id),
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    art = db.session.scalar(
        db.select(Article).where(Article.title == "عنوان خبر جديد مكتوب في الاختبار")
    )
    assert art is not None
    assert art.status is ArticleStatus.PUBLISHED
    assert art.published_at is not None


def test_create_article_rejects_short_body(client, users, category):
    login(client, "editor", "editor123")
    r = client.post(
        "/editor/articles/new",
        data={"title": "عنوان طويل بما يكفي للمرور", "body": "قصير", "status": "draft"},
    )
    assert r.status_code == 200
    assert db.session.scalar(db.select(db.func.count(Article.id))) == 0


def test_create_article_rejects_bad_image_url(client, users, category):
    login(client, "editor", "editor123")
    r = client.post(
        "/editor/articles/new",
        data={
            "title": "عنوان طويل بما يكفي للمرور",
            "body": VALID_BODY,
            "status": "draft",
            "cover_image_url": "javascript:alert(1)",
        },
    )
    assert r.status_code == 200
    assert db.session.scalar(db.select(db.func.count(Article.id))) == 0


def test_update_article_regenerates_slug(client, users, article):
    login(client, "editor", "editor123")
    old_slug = article.slug
    r = client.post(
        f"/editor/articles/{article.id}/edit",
        data={
            "title": "عنوان جديد مختلف كليا بعد التعديل",
            "body": VALID_BODY,
            "status": "published",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    db.session.refresh(article)
    assert article.slug != old_slug


def test_publish_toggles_status(client, users, draft):
    login(client, "editor", "editor123")
    client.post(f"/editor/articles/{draft.id}/publish", follow_redirects=True)
    db.session.refresh(draft)
    assert draft.status is ArticleStatus.PUBLISHED

    client.post(f"/editor/articles/{draft.id}/publish", follow_redirects=True)
    db.session.refresh(draft)
    assert draft.status is ArticleStatus.DRAFT
    assert draft.published_at is None


def test_publish_rejects_short_body(client, users):
    login(client, "editor", "editor123")
    short = Article(
        title="عنوان صالح لكن المتن قصير",
        body="قصير",
        status=ArticleStatus.DRAFT,
        author_id=users["editor"].id,
    )
    short.regenerate_slug()
    db.session.add(short)
    db.session.commit()

    r = client.post(f"/editor/articles/{short.id}/publish", follow_redirects=True)
    assert "80" in r.get_data(as_text=True)
    db.session.refresh(short)
    assert short.status is ArticleStatus.DRAFT


def test_delete_article_blocked_when_task_linked(client, users, article, task):
    login(client, "editor", "editor123")
    r = client.post(f"/editor/articles/{article.id}/delete", follow_redirects=True)
    assert "مرتبط" in r.get_data(as_text=True)
    assert db.session.get(Article, article.id) is not None


def test_delete_article_succeeds_when_unlinked(client, users, draft):
    login(client, "editor", "editor123")
    r = client.post(f"/editor/articles/{draft.id}/delete", follow_redirects=True)
    assert r.status_code == 200
    assert db.session.get(Article, draft.id) is None


def test_writer_cannot_create_article(client, users):
    login(client, "writer", "writer123")
    r = client.post(
        "/editor/articles/new",
        data={"title": "محاولة من كاتب", "body": VALID_BODY, "status": "draft"},
    )
    assert r.status_code == 403
    assert db.session.scalar(db.select(db.func.count(Article.id))) == 0


def test_editor_cannot_open_missing_article(client, users):
    login(client, "editor", "editor123")
    assert client.get("/editor/articles/9999/edit").status_code == 404


def test_stats_page_renders(client, users, article, task):
    login(client, "editor", "editor123")
    r = client.get("/editor/stats")
    assert r.status_code == 200
    assert "مقال منشور" in r.get_data(as_text=True)


# ============ صفحة التحرير: نماذج غير متداخلة ============


def _has_nested_form(html: str) -> bool:
    """يكشف <form> داخل <form> آخر: المتصفّح يتجاهل الداخلي فتتعطّل أزراره."""
    import re

    depth = 0
    for m in re.finditer(r"<form\b|</form\s*>", html, flags=re.IGNORECASE):
        if m.group().lower().startswith("</"):
            depth -= 1
        elif depth:
            return True
        else:
            depth += 1
    return False


def _tag_named(html: str, name: str) -> str:
    """أول وسم يحمل name="..." لفحص سِماته."""
    import re

    m = re.search(rf"<[a-z]+[^>]*\bname=\"{re.escape(name)}\"[^>]*>", html)
    return m.group() if m else ""


def test_edit_page_has_no_nested_forms(client, users, draft):
    """زر «حذف الخبر» يجب أن يكون داخل نموذج مستقل، لا داخل نموذج التعديل."""
    login(client, "editor", "editor123")
    body = client.get(f"/editor/articles/{draft.id}/edit").get_data(as_text=True)
    assert not _has_nested_form(body), "نموذج متداخل يجعل زر الحذف ي submit التعديل"
    assert 'id="article-form"' in body
    assert f'action="/editor/articles/{draft.id}/delete"' in body
    assert f'action="/editor/articles/{draft.id}/publish"' in body


def test_edit_page_keeps_sidebar_fields_in_the_article_form(client, users, draft):
    """الحقول الجانبية خارج النموذج صياغياً لكنها مرتبطة به بـ form="article-form"."""
    login(client, "editor", "editor123")
    body = client.get(f"/editor/articles/{draft.id}/edit").get_data(as_text=True)
    for name in ("category_id", "cover_image_url", "status"):
        tag = _tag_named(body, name)
        assert tag, f"الحقل {name} غير موجود"
        assert 'form="article-form"' in tag, f"{name} لم يُربط بالنموذج الرئيس"
    import re

    btn = re.search(r"<button[^>]*form=\"article-form\"[^>]*>", body)
    assert btn, "زر الحفظ غير مرتبط بالنموذج الرئيس"
    assert 'type="submit"' in btn.group()


def test_edit_page_saves_through_the_associated_form(client, users, draft):
    """الحفظ ما زال يصل: الحقول المرتبطة تُرسَل مع النموذج عند الضغط."""
    login(client, "editor", "editor123")
    r = client.post(
        f"/editor/articles/{draft.id}/edit",
        data={"title": "عنوان محفوظ بعد إعادة بناء النموذج", "body": VALID_BODY,
              "status": "draft", "category_id": "0"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    db.session.refresh(draft)
    assert draft.title == "عنوان محفوظ بعد إعادة بناء النموذج"


# ============ الحذف الجماعي من القائمة ============


def _new_draft(users, title: str) -> Article:
    art = Article(title=title, body=VALID_BODY, status=ArticleStatus.DRAFT,
                  author_id=users["editor"].id)
    art.regenerate_slug()
    db.session.add(art)
    db.session.commit()
    return art


def test_editor_list_offers_bulk_selection(client, users, article):
    login(client, "editor", "editor123")
    body = client.get("/editor").get_data(as_text=True)
    assert 'action="/editor/articles/delete-selected"' in body
    assert 'id="select-all"' in body
    assert 'id="bulk-delete-btn"' in body
    assert f'name="ids" value="{article.id}"' in body


def test_editor_list_puts_edit_and_preview_actions_side_by_side(client, users, article):
    """الزرّان في خلية واحدة بلا التفاف: الصنف t-actions يمنع ظهورهما فوق بعض."""
    import re

    login(client, "editor", "editor123")
    body = client.get("/editor").get_data(as_text=True)
    cell = re.search(r'<td class="t-actions">(.*?)</td>', body, re.S)
    assert cell, "خلية الإجراءات يجب أن تحمل الصنف t-actions (white-space: nowrap)"
    inner = cell.group(1)
    assert f'href="/editor/articles/{article.id}/edit"' in inner
    assert "معاينة" in inner and "تحرير" in inner


def test_delete_selected_removes_checked_articles_only(client, users, article, draft, task):
    """المرتبط بمهمة يبقى ويُبلَّغ عنه، والباقي يُحذف."""
    login(client, "editor", "editor123")
    extra = _new_draft(users, "مسودة ثانية في اختبار الحذف الجماعي")
    r = client.post(
        "/editor/articles/delete-selected",
        data={"ids": [str(draft.id), str(extra.id), str(article.id)]},
        follow_redirects=True,
    )
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert db.session.get(Article, draft.id) is None
    assert db.session.get(Article, extra.id) is None
    assert db.session.get(Article, article.id) is not None
    assert "تم حذف" in body
    assert "تعذّر حذف" in body
    assert article.title in body


def test_delete_selected_ignores_bad_and_duplicate_ids(client, users, draft):
    login(client, "editor", "editor123")
    r = client.post(
        "/editor/articles/delete-selected",
        data={"ids": ["abc", str(draft.id), str(draft.id)]},
        follow_redirects=True,
    )
    body = r.get_data(as_text=True)
    assert db.session.get(Article, draft.id) is None
    assert "تم حذف مقالة واحدة" in body  # التكرار يُحذف مرّة واحدة


def test_delete_selected_without_selection_flashes_error(client, users, article):
    login(client, "editor", "editor123")
    r = client.post("/editor/articles/delete-selected", follow_redirects=True)
    assert "لم تختر أي مقالة" in r.get_data(as_text=True)
    assert db.session.get(Article, article.id) is not None


def test_delete_selected_keeps_status_filter_and_page(client, users, draft, article):
    login(client, "editor", "editor123")
    r = client.post(
        "/editor/articles/delete-selected",
        data={"ids": str(draft.id), "status": "draft", "page": "3"},
    )
    assert r.status_code == 302
    location = r.headers["Location"]
    assert "status=draft" in location and "page=3" in location
    assert db.session.get(Article, article.id) is not None


def test_writer_cannot_bulk_delete(client, users, article):
    login(client, "writer", "writer123")
    r = client.post("/editor/articles/delete-selected", data={"ids": str(article.id)})
    assert r.status_code == 403
    assert db.session.get(Article, article.id) is not None


# ============ الحذف الإجباري للمهام (مدير فقط) ============


def test_admin_force_delete_removes_article_and_its_tasks(client, users, article, task):
    login(client, "admin", "admin123")
    r = client.post(
        f"/editor/articles/{article.id}/delete",
        data={"delete_tasks": "1"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert db.session.get(Article, article.id) is None
    assert db.session.get(Task, task.id) is None
    assert "تم حذف الخبر" in r.get_data(as_text=True)


def test_admin_delete_without_force_still_blocks_linked_article(client, users, article, task):
    login(client, "admin", "admin123")
    r = client.post(f"/editor/articles/{article.id}/delete", follow_redirects=True)
    assert "لا يمكن حذف" in r.get_data(as_text=True)
    assert db.session.get(Article, article.id) is not None
    assert db.session.get(Task, task.id) is not None


def test_editor_cannot_force_delete_linked_article(client, users, article, task):
    """المربّع إداري: طلب المحرّر يُتجاهَل ويبقى المنع قائماً."""
    login(client, "editor", "editor123")
    r = client.post(
        f"/editor/articles/{article.id}/delete",
        data={"delete_tasks": "1"},
        follow_redirects=True,
    )
    assert "لا يمكن حذف" in r.get_data(as_text=True)
    assert db.session.get(Article, article.id) is not None
    assert db.session.get(Task, task.id) is not None


def test_edit_page_shows_force_checkbox_to_admin(client, users, article, task):
    login(client, "admin", "admin123")
    body = client.get(f"/editor/articles/{article.id}/edit").get_data(as_text=True)
    assert 'name="delete_tasks"' in body


def test_edit_page_hides_force_checkbox_from_editor(client, users, article, task):
    """المربّع إداري: محرّر لا يراه لأن الحذف القسري ليس من صلاحياته."""
    login(client, "editor", "editor123")
    body = client.get(f"/editor/articles/{article.id}/edit").get_data(as_text=True)
    assert 'name="delete_tasks"' not in body


def test_admin_bulk_force_delete_removes_linked_articles_and_tasks(client, users, article, draft, task):
    login(client, "admin", "admin123")
    r = client.post(
        "/editor/articles/delete-selected",
        data={"ids": [str(article.id), str(draft.id)], "delete_tasks": "1"},
        follow_redirects=True,
    )
    body = r.get_data(as_text=True)
    assert db.session.get(Article, article.id) is None
    assert db.session.get(Task, task.id) is None
    assert db.session.get(Article, draft.id) is None
    assert "تم حذف" in body
    assert "مرتبطة بها" in body


def test_editor_bulk_force_request_is_ignored(client, users, article, task):
    login(client, "editor", "editor123")
    r = client.post(
        "/editor/articles/delete-selected",
        data={"ids": str(article.id), "delete_tasks": "1"},
        follow_redirects=True,
    )
    assert "تعذّر حذف" in r.get_data(as_text=True)
    assert db.session.get(Article, article.id) is not None
    assert db.session.get(Task, task.id) is not None