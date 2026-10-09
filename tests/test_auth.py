"""اختبارات المصادقة والصلاحيات."""

from __future__ import annotations

from tests.conftest import login


def test_login_page_renders(client, app):
    r = client.get("/auth/login")
    assert r.status_code == 200
    assert "دخول الموظفين" in r.get_data(as_text=True)


def test_login_succeeds_with_valid_credentials(client, users):
    r = login(client, "editor", "editor123")
    assert r.status_code == 200
    assert "أهلاً بك" in r.get_data(as_text=True)


def test_login_fails_with_wrong_password(client, users):
    # 6 أحرف على الأقل حتى يمرّ Length ويصل الفشل إلى فحص كلمة المرور
    assert "غير صحيحة" in login(client, "editor", "wrongpass").get_data(as_text=True)


def test_login_fails_with_unknown_user(client, app):
    assert "غير صحيحة" in login(client, "ghost", "whatever").get_data(as_text=True)


def test_logout_requires_post(client, users):
    login(client, "editor", "editor123")
    assert client.get("/auth/logout").status_code == 405


def test_logout_via_post_ends_session(client, users):
    login(client, "editor", "editor123")
    r = client.post("/auth/logout")
    assert r.status_code == 302
    assert client.get("/editor").status_code == 302


def test_editor_redirects_anonymous_user(client, app):
    r = client.get("/editor")
    assert r.status_code == 302
    assert "/auth/login" in r.headers["Location"]


def test_editor_forbidden_for_writer(client, users):
    login(client, "writer", "writer123")
    assert client.get("/editor").status_code == 403


def test_editor_allowed_for_editor_role(client, users, article):
    login(client, "editor", "editor123")
    assert client.get("/editor").status_code == 200


def test_editor_allowed_for_admin(client, users, article):
    login(client, "admin", "admin123")
    assert client.get("/editor").status_code == 200


def test_tasks_redirects_anonymous_user(client, app):
    r = client.get("/tasks")
    assert r.status_code == 302
    assert "/auth/login" in r.headers["Location"]


def test_tasks_allowed_for_writer(client, users):
    login(client, "writer", "writer123")
    assert client.get("/tasks").status_code == 200


def test_open_redirect_is_blocked(client, users):
    """?next= لموقع خارجي يجب أن يُتجاهل."""
    r = client.post(
        "/auth/login?next=https://evil.example.com/steal",
        data={"username": "editor", "password": "editor123"},
    )
    assert r.status_code == 302
    assert "evil.example.com" not in r.headers["Location"]


def test_protocol_relative_next_is_blocked(client, users):
    """//evil.example.com يبدو نسبياً لكنه رابط كامل."""
    r = client.post(
        "/auth/login?next=//evil.example.com",
        data={"username": "editor", "password": "editor123"},
    )
    assert r.status_code == 302
    assert "evil.example.com" not in r.headers["Location"]


def test_next_within_site_is_followed(client, users, article):
    r = client.post(
        "/auth/login?next=/editor",
        data={"username": "editor", "password": "editor123"},
    )
    assert r.status_code == 302
    assert "/editor" in r.headers["Location"]


def test_next_target_has_no_trailing_question_mark(client, app):
    """request.full_path كان يضيف '?' فينتج /auth/login?next=/editor?"""
    r = client.get("/editor")
    assert r.status_code == 302
    location = r.headers["Location"]
    assert "next=/editor" in location
    assert not location.endswith("?")


def test_login_form_rejects_short_username(client, app):
    r = client.post("/auth/login", data={"username": "ab", "password": "editor123"})
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "الطول المسموح" in body or "هذا الحقل مطلوب" in body


def test_authenticated_login_redirects_home(client, users):
    login(client, "editor", "editor123")
    r = client.get("/auth/login")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/")