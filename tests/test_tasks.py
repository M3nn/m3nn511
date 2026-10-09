"""اختبارات إدارة المهام: إنشاء، تعديل، تغيير حالة، نطاق رؤية الكاتب."""

from __future__ import annotations

import datetime as dt

from app.extensions import db
from app.models import Task, TaskStatus
from tests.conftest import login

VALID_TITLE = "عنوان مهمة صالح وطويل بما يكفي"


def _new_task(client, title=VALID_TITLE, **extra):
    data = {"title": title, "status": "todo", "priority": "med"}
    data.update(extra)
    return client.post("/tasks/new", data=data, follow_redirects=True)


def test_task_list_renders(client, users, task):
    login(client, "editor", "editor123")
    r = client.get("/tasks")
    assert r.status_code == 200
    assert task.title in r.get_data(as_text=True)


def test_create_task_as_editor(client, users):
    login(client, "editor", "editor123")
    r = _new_task(client, assignee_id=str(users["writer"].id))
    assert r.status_code == 200
    new = db.session.scalar(db.select(Task).where(Task.title == VALID_TITLE))
    assert new is not None
    assert new.status is TaskStatus.TODO
    assert new.assignee_id == users["writer"].id


def test_create_task_rejects_short_title(client, users):
    login(client, "editor", "editor123")
    _new_task(client, title="قصير")
    assert db.session.scalar(db.select(db.func.count(Task.id))) == 0


def test_prefill_from_ai_suggestion(client, users):
    """زر «أضف» من اقتراح AI يفتح النموذج مع العنوان مملوءا."""
    login(client, "editor", "editor123")
    r = client.get("/tasks/new?title=مهمة+مقترحة+من+النموذج&priority=high")
    body = r.get_data(as_text=True)
    assert "مهمة مقترحة من النموذج" in body


def test_advance_status_persists(client, users, task):
    login(client, "editor", "editor123")
    r = client.post(f"/tasks/{task.id}/advance", headers={"HX-Request": "true"})
    assert r.status_code == 200
    db.session.refresh(task)
    assert task.status is TaskStatus.DOING

    client.post(f"/tasks/{task.id}/advance", headers={"HX-Request": "true"})
    db.session.refresh(task)
    assert task.status is TaskStatus.DONE


def test_advance_returns_row_fragment(client, users, task):
    login(client, "editor", "editor123")
    r = client.post(f"/tasks/{task.id}/advance", headers={"HX-Request": "true"})
    body = r.get_data(as_text=True)
    assert f'id="task-{task.id}"' in body
    assert "<html" not in body


def test_advance_on_done_task_is_noop(client, users, task):
    task.status = TaskStatus.DONE
    db.session.commit()
    login(client, "editor", "editor123")
    client.post(f"/tasks/{task.id}/advance", headers={"HX-Request": "true"})
    db.session.refresh(task)
    assert task.status is TaskStatus.DONE


def test_set_status_rejects_invalid_value(client, users, task):
    login(client, "editor", "editor123")
    r = client.post(f"/tasks/{task.id}/status", data={"status": "hacked"},
                    follow_redirects=True)
    assert "معروفة" in r.get_data(as_text=True)
    db.session.refresh(task)
    assert task.status is TaskStatus.TODO


def test_set_status_accepts_valid_value(client, users, task):
    login(client, "editor", "editor123")
    client.post(f"/tasks/{task.id}/status", data={"status": "done"},
                follow_redirects=True)
    db.session.refresh(task)
    assert task.status is TaskStatus.DONE


def test_writer_sees_only_own_tasks(client, users, task):
    other = Task(title="مهمة محرر لا يملك الكاتب رؤيتها", assignee_id=users["editor"].id)
    db.session.add(other)
    db.session.commit()

    login(client, "writer", "writer123")
    body = client.get("/tasks").get_data(as_text=True)
    assert task.title in body
    assert other.title not in body


def test_editor_sees_all_tasks(client, users, task):
    other = Task(title="مهمة تخص محررا آخر", assignee_id=users["writer"].id)
    db.session.add(other)
    db.session.commit()

    login(client, "editor", "editor123")
    body = client.get("/tasks").get_data(as_text=True)
    assert task.title in body
    assert other.title in body


def test_writer_cannot_open_others_task(client, users, task):
    other = Task(title="مهمة محرر محمية", assignee_id=users["editor"].id)
    db.session.add(other)
    db.session.commit()

    login(client, "writer", "writer123")
    # 404 وليس 403 حتى لا نكشف وجود المهمة
    assert client.get(f"/tasks/{other.id}/edit").status_code == 404


def test_writer_cannot_reassign_task(client, users, task):
    login(client, "writer", "writer123")
    client.post(
        f"/tasks/{task.id}/edit",
        data={
            "title": task.title,
            "status": task.status.value,
            "priority": task.priority.value,
            "assignee_id": str(users["admin"].id),
        },
        follow_redirects=True,
    )
    db.session.refresh(task)
    assert task.assignee_id == users["writer"].id


def test_new_task_created_by_writer_is_assigned_to_self(client, users):
    login(client, "writer", "writer123")
    _new_task(client, assignee_id=str(users["admin"].id))
    new = db.session.scalar(db.select(Task).where(Task.title == VALID_TITLE))
    assert new is not None
    assert new.assignee_id == users["writer"].id


def test_reject_past_due_date(client, users):
    login(client, "editor", "editor123")
    past = (dt.date.today() - dt.timedelta(days=3)).isoformat()
    r = _new_task(client, due_date=past)
    assert "الماضي" in r.get_data(as_text=True)
    assert db.session.scalar(db.select(db.func.count(Task.id))) == 0


def test_delete_task(client, users, task):
    login(client, "editor", "editor123")
    client.post(f"/tasks/{task.id}/delete", follow_redirects=True)
    assert db.session.get(Task, task.id) is None
