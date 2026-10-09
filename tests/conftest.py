"""تهيئات الاختبارات: تطبيق معزول + قاعدة في الذاكرة لكل اختبار."""
from __future__ import annotations

import atexit
import os
import shutil
import tempfile

import pytest

# ---- عزل السجلات: قبل استيراد app، لأن Config يقرأ LOG_DIR عند الاستيراد ----
# بدون هذا يكتب الاختبار في logs/app.log الحقيقي فيمتلئ ب-stack-traces
# مقصودة من اختبارات الذكاء الاصطناعي، ويصبح سجل التشغيل غير صالح للفحص.
TEST_LOG_DIR = tempfile.mkdtemp(prefix="nassa_test_logs_")
os.environ["LOG_DIR"] = TEST_LOG_DIR
os.environ["LOG_FILE"] = "test.log"
os.environ["LOG_TO_STDERR"] = "0"
atexit.register(shutil.rmtree, TEST_LOG_DIR, True)

from app import create_app  # noqa: E402
from app.extensions import db as _db
from app.models import (
    Article,
    ArticleStatus,
    Category,
    Priority,
    Role,
    Task,
    TaskStatus,
    User,
)


@pytest.fixture()
def app():
    """تطبيق معزول: قاعدة في الذاكرة، وسجلات في مجلد مؤقّت (TEST_LOG_DIR).

    لا يلمس instance/app.db ولا logs/ إطلاقاً."""
    application = create_app("test")
    with application.app_context():
        _db.create_all()
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def make_user(username: str, password: str, role: Role) -> User:
    user = User(username=username, display_name=f"مستخدم {username}", role=role)
    user.set_password(password)
    _db.session.add(user)
    _db.session.commit()
    return user


@pytest.fixture()
def users(app):
    return {
        "admin": make_user("admin", "admin123", Role.ADMIN),
        "editor": make_user("editor", "editor123", Role.EDITOR),
        "writer": make_user("writer", "writer123", Role.WRITER),
    }


@pytest.fixture()
def category(app):
    cat = Category(name="كرة القدم", slug="كرة-القدم", sort_order=1)
    _db.session.add(cat)
    _db.session.commit()
    return cat


LONG_BODY = "\n\n".join([
    "أنهى الفريق مباراته أمام الهلال بفوز كبير في الديربي الذي جمع الفريقين على المدرجات." * 2,
    "سجل المهاجم هدفين في الشوط الأول قبل أن يضيف زميله الهدف الثالث في الشوط الثاني." * 2,
    "أدار المدرب المباراة بذكاء من خلال خط الوسط وحافظ على توازن الفريق." * 2,
    "خرج الجمهور راضياً بالأداء الرائع الذي قدمه الفريق خلال التسعين دقيقة." * 2,
])


@pytest.fixture()
def article(app, users, category):
    art = Article(
        title="النصر يفوز على الهلال بثلاثية في الديربي",
        body=LONG_BODY,
        summary="فوز كبير بثلاثية في الديربي.",
        status=ArticleStatus.PUBLISHED,
        category_id=category.id,
        author_id=users["editor"].id,
    )
    art.regenerate_slug()
    art.published_at = art.created_at
    _db.session.add(art)
    _db.session.commit()
    return art


@pytest.fixture()
def draft(app, users, category):
    art = Article(
        title="مسودة خبر لم ينشر بعد في الموقع",
        body="متن المسودة التجريبية طويل بما يكفي لاجتياز حد الطول الأدنى المطلوب. " * 2,
        status=ArticleStatus.DRAFT,
        category_id=category.id,
        author_id=users["editor"].id,
    )
    art.regenerate_slug()
    _db.session.add(art)
    _db.session.commit()
    return art


@pytest.fixture()
def task(app, users, article):
    t = Task(
        title="مراجعة مسودة خبر الديربي قبل النشر",
        status=TaskStatus.TODO,
        priority=Priority.HIGH,
        assignee_id=users["writer"].id,
        article_id=article.id,
    )
    _db.session.add(t)
    _db.session.commit()
    return t


def login(client, username: str, password: str):
    """تسجيل دخول عبر POST الحقيقي، لا عبر كائن المستخدم."""
    return client.post(
        "/auth/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )
