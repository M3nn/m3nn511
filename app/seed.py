"""بيانات البذر التجريبية — تُنشأ بأمر `flask seed` فقط.

محتوى واقعي لتغطية كل حالات الواجهة: أخبار منشورة، مسودات، مقال بلا ملخص،
مهام في الحالات الثلاث، ومهمة متأخرة. الاستدعاء مراراً لا يكرّر شيئاً.
"""
from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import func, select

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

log = logging.getLogger("app.seed")

USERS = [
    ("admin", "admin123", "مدير النظام", Role.ADMIN),
    ("editor", "editor123", "عبدالله المحرر", Role.EDITOR),
    ("writer", "writer123", "سارة الكاتب", Role.WRITER),
]

CATEGORIES = [
    ("كرة القدم", "كرة-القدم", 1),
    ("كرة السلة", "كرة-السلة", 2),
    ("رياضات مختلفة", "رياضات-مختلفة", 3),
    ("تحليلات", "تحليلات", 4),
    ("انتقالات", "انتقالات", 5),
]

P = ArticleStatus.PUBLISHED
D = ArticleStatus.DRAFT


def para(*sentences: str) -> str:
    """يجمع جمل الفقرة في نص واحد. تُخزَّن الفقرات مفصولة بسطر فارغ."""
    return "\n\n".join(sentences)


# (العنوان، التصنيف، الحالة، الملخص أو None، المتن، عدد الأيام منذ النشر)
ARTICLES = [
    (
        "النصر يفتتح الدوري بفوز عريض وثلاثية في الشوط الثاني",
        "كرة القدم",
        P,
        None,
        para(
            "أنهى الفريق مباراته الافتتاحية بفوز أربعة أهداف مقابل هدف.",
            "بدأ اللقاء متكافئا، لكن التحول جاء بعد استراحة الشوط الأول.",
            "سجل ثلاثة أهداف متتالية خلال أقل من عشر دقائق.",
            "أكد المدرب أن الفريق ما زال في بدايته يتعلم.",
        ),
        0,
    ),
    (
        "مدرب النصر: الالتزام التكتيكي هو عنوان النجاح",
        "تحليلات",
        P,
        None,
        para(
            "أكد المدرب أن الالتزام التكتيكي هو مقياس النجاح الحقيقي.",
            "أضاف أن الفريق تعلم كيف يقرأ مباراة مغلقة ثم يفتحها.",
            "وقال إن هذا يحتاج تكرارات يومية حتى يصبح عادة.",
        ),
        1,
    ),
    (
        "انتقالات: مصادر تكشف قرب انتقال لاعب الوسط",
        "انتقالات",
        P,
        "قال مصدر قريب إن الصفقة قد تتم خلال أيام.",
        para(
            "أوردت تقارير صحفية أن النادي يقترب من التعاقد مع لاعب وسط دولي.",
            "استمرت المفاوضات أكثر من شهرين بين الناديين.",
            "ويرجح أن الاتفاق سيتوقف على إتمام صفقة لاعب آخر.",
            "لم يطلب النادي التعليق على التقارير حتى الآن.",
        ),
        2,
    ),
    (
        "فريق السلة يفوز في مباراته القارية بفارق عشرين نقطة",
        "كرة السلة",
        P,
        None,
        para(
            "حقق فريق كرة السلة فوزا مريحا في مباراته القارية.",
            "سجل عدد من السلاسل المتتالية في الربع الثالث.",
            "غيّرت هذه السلاسل مجرى اللقاء كليا.",
        ),
        3,
    ),
    (
        "عدّاء سعودي يحطّم رقمه الشخصي في سباق المضمار",
        "رياضات مختلفة",
        P,
        None,
        para(
            "حطم العداء السعودي رقمه الشخصي في سباق على مضمار معبد.",
            "جاء الزمن الجديد هو الأفضل في مسيرته كاملة.",
            "أعاد السباق مرتين للتحقق من الرقم المسجل.",
        ),
        4,
    ),
    (
        "تحليل: ثلاثة أسباب تقف خلف تحول النصر",
        "تحليلات",
        P,
        None,
        para(
            "العامل الأول هو ارتفاع شدة الضغط على حامل الكرة.",
            "العامل الثاني هو نقل الكرة إلى الجهة اليسرى.",
            "العامل الثالث هو استغلال ضعف المراوغة في التحول الدفاعي.",
            "هذه العوامل تتضافر، ولا يكفي عامل واحد لتفسير ما حدث.",
        ),
        5,
    ),
    (
        "النصر يكمل تحضيرات معسكره في الرياض",
        "كرة القدم",
        P,
        None,
        para(
            "أكمل الفريق برنامجه في المعسكر وسط سلسلة تدريبات مغلقة.",
            "ركزت التدريبات على الانسيابية في خط الوسط.",
            "واختبر المدرب تشكيلة جديدة في مركز الظهير الأيمن.",
        ),
        6,
    ),
    (
        "أرقام المباراة: إحصاءات من آخر خمس مواجهات",
        "تحليلات",
        P,
        None,
        para(
            "التمرير الصحيح وسرعة استرجاع الكرة ليسا مجرد أرقام.",
            "هما مؤشرات على مستوى الجاهزية الذهنية للفريق.",
            "سجل الفريق معدلاً جيداً في الاسترجاع.",
            "لكنه تراجع في دقة التسديد من مسافات بعيدة.",
        ),
        7,
    ),
    (
        "مسودة: تقرير مفصل عن المواجهة الأخيرة",
        "كرة القدم",
        D,
        None,
        para(
            "مسودة قيد الإعداد تتناول تفاصيل المواجهة الأخيرة.",
            "تغطي المسودة تحليل اللقطات المهمة في كل شوط.",
            "لا تنشر قبل المراجعة النهائية من المحرر.",
        ),
        8,
    ),
    (
        "مسودة: قائمة الانتقالات الصيفية",
        "انتقالات",
        D,
        None,
        para(
            "مسودة تجمع أبرز الأسماء المتداولة في سوق الانتقالات.",
            "تحتاج المسودة تدقيق الأسماء من مصادر رسمية.",
            "النص تحت المراجعة في قسم التحرير.",
        ),
        9,
    ),
    (
        "خمسة لاعبين يخطفون الأنظار في الجولة الأخيرة",
        "تحليلات",
        P,
        None,
        para(
            "قدّم خمسة لاعبين مستويات لافتة في الجولة الأخيرة.",
            "برز منهم جناحان صنعا أغلب الفرص الخطيرة.",
            "وأظهر مدافع شاب نضجا في قراءة الكرات العرضية.",
        ),
        10,
    ),
    (
        "فريق السلة يستعد للاستحقاق الآسيوي بمعسكر مغلق",
        "كرة السلة",
        P,
        None,
        para(
            "دخل فريق السلة معسكرا مغلقا استعدادا للاستحقاق الآسيوي.",
            "يركز الجهاز الفني على رفع دقة التسديد من خارج القوس.",
            "وسيخوض الفريق مباراتين وديتين قبل انطلاق البطولة.",
        ),
        11,
    ),
    (
        "انتقالات: تجديد عقد الظهير الأيسر يقترب من الحسم",
        "انتقالات",
        P,
        "المفاوضات في مراحلها الأخيرة بحسب مصدر مقرّب.",
        para(
            "اقتربت إدارة النادي من حسم تجديد عقد الظهير الأيسر.",
            "تضمن العرض تعديلا في الشرط الجزائي لمصلحة النادي.",
            "وينتظر أن يُعلن التجديد رسميا خلال الأيام القادمة.",
        ),
        12,
    ),
    (
        "الأرقام لا تكذب: هكذا تغيّر خط الدفاع هذا الموسم",
        "تحليلات",
        P,
        None,
        para(
            "انخفض عدد الأهداف المستقبلة مقارنة بالموسم الماضي.",
            "يعود ذلك إلى تقليص المساحات خلف خط الوسط.",
            "لكن الاستحواذ على الكرة تراجع في المقابل.",
        ),
        13,
    ),
    (
        "افتتاح ملعب جديد بطاقة استيعابية كبيرة",
        "رياضات مختلفة",
        P,
        None,
        para(
            "أعلن عن افتتاح ملعب جديد بطاقة استيعابية كبيرة.",
            "صُمّم الملعب وفق أحدث معايير الإضاءة والعشب.",
            "وسيحتضن أولى مبارياته في الجولة المقبلة.",
        ),
        14,
    ),
    (
        "جدول مباريات الأسبوع: مواجهات قوية تنتظر الجماهير",
        "كرة القدم",
        P,
        None,
        para(
            "يشهد الأسبوع مواجهات قوية بين فرق الصدارة.",
            "أبرزها لقاء القمة الذي يجمع المتصدر بالوصيف.",
            "وتقام بقية المباريات على مدار ثلاثة أيام.",
        ),
        15,
    ),
]

# (العنوان، الحالة، الأولوية، إزاحة أيام الاستحقاق)
TASKS = [
    ("كتابة تقرير مباراة الأمس", TaskStatus.DONE, Priority.MED, -3),
    ("مراجعة مسودة خبر الانتقالات", TaskStatus.DOING, Priority.HIGH, 1),
    ("إعداد قائمة أفضل خمسة لاعبين", TaskStatus.TODO, Priority.LOW, 5),
    ("تدقيق الأرقام في خبر الإحصاءات", TaskStatus.TODO, Priority.HIGH, -1),
    ("تصوير غلاف العدد القادم", TaskStatus.TODO, Priority.MED, 2),
    ("تحديث صفحة التصنيفات", TaskStatus.DOING, Priority.LOW, 0),
]


def seed_all() -> list[str]:
    """يبذر كل شيء ويُرجع أسطرا جاهزة للطباعة. آمن للتكرار."""
    from app.models import AIUsage  # noqa: F401 - يضمن تسجيل كل الجداول

    db.create_all()
    users = _seed_users()
    categories = _seed_categories()
    articles = _seed_articles(users, categories)
    tasks = _seed_tasks(users, articles)
    return [
        f"✔ المستخدمون: {len(users)}",
        f"✔ التصنيفات: {len(categories)}",
        f"✔ المقالات: {len(articles)}",
        f"✔ المهام: {tasks}",
    ]


def seed_content(author: User, assignee: User | None = None) -> list[str]:
    """يعبّئ التصنيفات والأخبار والمهام فقط (بلا إنشاء حسابات موظفين تجريبية).

    يُستخدم عند الإقلاع على استضافة بلا تخزين دائم (Render المجاني) كي تظهر
    المنصة كاملة بعد كل إعادة تشغيل، مع إسناد المحتوى للمسؤول. آمن للتكرار."""
    from app.models import AIUsage  # noqa: F401 - يضمن تسجيل كل الجداول

    assignee = assignee or author
    db.create_all()
    categories = _seed_categories()
    articles = _seed_articles_for([author], categories)
    tasks = _seed_tasks_for([assignee], articles)
    return [
        f"✔ التصنيفات: {len(categories)}",
        f"✔ المقالات: {len(articles)}",
        f"✔ المهام: {tasks}",
    ]


def _seed_users() -> dict[str, User]:
    result = {}
    for username, password, display, role in USERS:
        user = db.session.scalar(select(User).where(User.username == username))
        if user is None:
            user = User(username=username, display_name=display, role=role)
            user.set_password(password)
            db.session.add(user)
        result[username] = user
    db.session.commit()
    return result


def _seed_categories() -> dict[str, Category]:
    result = {}
    for name, slug, order in CATEGORIES:
        cat = db.session.scalar(select(Category).where(Category.slug == slug))
        if cat is None:
            cat = Category(name=name, slug=slug, sort_order=order)
            db.session.add(cat)
        result[name] = cat
    db.session.commit()
    return result


def _seed_articles(users, categories) -> list[Article]:
    return _seed_articles_for([users["editor"], users["writer"]], categories)


def _seed_articles_for(authors, categories) -> list[Article]:
    now = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    created = []

    for i, (title, cat_name, status, summary, body, days_ago) in enumerate(ARTICLES):
        if db.session.scalar(select(Article.id).where(Article.title == title)):
            continue
        published_at = now - dt.timedelta(days=days_ago, hours=2) if status is P else None
        art = Article(
            title=title,
            slug=slugify(title),
            summary=summary,
            body=body,
            cover_image_url=None,
            status=status,
            category_id=categories[cat_name].id if cat_name in categories else None,
            author_id=authors[i % len(authors)].id,
            published_at=published_at,
            created_at=now - dt.timedelta(days=days_ago + 1),
            updated_at=now - dt.timedelta(days=days_ago),
        )
        db.session.add(art)
        created.append(art)

    db.session.commit()
    return created


def _seed_tasks(users, articles) -> int:
    """يبذر المهام مرة واحدة فقط. يُرجع عدد ما أُنشئ."""
    return _seed_tasks_for([users["editor"], users["writer"], users["admin"]], articles)


def _seed_tasks_for(assignees, articles) -> int:
    if db.session.scalar(select(func.count(Task.id))):
        log.info("seed.tasks_skipped already_present")
        return 0

    today = dt.date.today()
    for i, (title, status, priority, offset) in enumerate(TASKS):
        db.session.add(
            Task(
                title=title,
                description=None,
                status=status,
                priority=priority,
                due_date=today + dt.timedelta(days=offset),
                assignee_id=assignees[i % len(assignees)].id,
                article_id=articles[i].id if i < len(articles) else None,
            )
        )
    db.session.commit()
    return len(TASKS)
