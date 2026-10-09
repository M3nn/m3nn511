"""أداة سطر أوامر لإدارة كلمات مرور المستخدمين بأمان (محلياً أو على الخادم).

لا تُقبل كلمة المرور كوسيط سطر أوامر إطلاقاً — كي لا تتسرّب إلى سجل المحطة
(shell history) ولا إلى قائمة العمليات — بل تُدخل بطلب آمن عبر ``getpass``
مع تأكيد وحد أدنى من الطول.

الاستخدام:
    change_passwords.py --list
    change_passwords.py admin                 # تغيير كلمة مرور مستخدم موجود
    change_passwords.py                       # اختيار من قائمة تفاعلية
    change_passwords.py --create chief --role admin --display "رئيس التحرير"

بعد التنفيذ ادخل للتأكد فوراً، وتأكد أن كلمات مرور التجربة (admin123 / editor123 /
writer123) لم تعد صالحة. من الأفضل حذف الملف من الخادم بعد الاستخدام.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

# يسمح بتشغيله من أي مجلد وليس من جذر المشروع فقط
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import ROLE_LABELS, Role, User  # noqa: E402

MIN_PASSWORD_LENGTH = 8


def _role(value: str | None) -> Role | None:
    if not value:
        return None
    try:
        return Role(value)
    except ValueError:
        choices = ", ".join(r.value for r in Role)
        print(f"  ✗ دور غير معروف «{value}» — اختر من: {choices}")
        return None


def list_users(app) -> int:
    """يطبع كل المستخدمين ويعيد عددهم."""
    with app.app_context():
        users = db.session.scalars(db.select(User).order_by(User.username)).all()
    if not users:
        print("  لا يوجد مستخدمون بعد — شغّل أولاً: flask --app run seed")
        return 0
    for user in users:
        label = ROLE_LABELS.get(user.role, str(user.role))
        print(f"  - {user.username:<20} ({label})  {user.display_name}")
    return len(users)


def pick_interactively(app) -> str | None:
    """قائمة مرقّمة لاختيار مستخدم، أو ``q`` للخروج."""
    with app.app_context():
        users = db.session.scalars(db.select(User).order_by(User.username)).all()
    if not users:
        print("  لا يوجد مستخدمون بعد — استخدم: change_passwords.py --create")
        return None
    for index, user in enumerate(users, 1):
        label = ROLE_LABELS.get(user.role, str(user.role))
        print(f"  {index}) {user.username} — {label}")
    while True:
        choice = input("  اختر رقماً (أو q للخروج): ").strip()
        if choice.lower() in {"q", ""}:
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(users):
            return users[int(choice) - 1].username
        print("  ✗ اختيار غير صالح.")


def change(app, username: str, password: str,
           display: str | None = None, role: Role | None = None) -> bool:
    """يحدّث كلمة مرور المستخدم، أو ينشئه مع الدور عند تمرير ``role``.

    يعيد ``True`` عند النجاح، و``False`` عندما لا يوجد المستخدم بلا ``--create``
    (الوظيفة صافية للاختبارات — النداء التفاعلي يتم في ``main``)."""
    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.username == username))
        created = False
        if user is None:
            if role is None:
                print(
                    f"  ✗ لا يوجد مستخدم اسمه «{username}». "
                    "يمكنك إنشاؤه بـ: --create --role <admin|editor|writer>"
                )
                return False
            user = User(username=username, display_name=display or username, role=role)
            db.session.add(user)
            created = True
        user.set_password(password)
        db.session.commit()
        action = "أُنشئ" if created else "حُدّثت كلمة مرور"
        label = ROLE_LABELS.get(user.role, str(user.role))
        print(f"  ✔ {action} «{username}» ({label}) — جرّب الدخول فوراً.")
        return True


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="change_passwords.py",
        description="تغيير كلمات مرور المستخدمين بأمان (بدون تمريرها في الأمر).",
    )
    parser.add_argument("username", nargs="?", help="اسم المستخدم (اختياري؛ بدونه قائمة تفاعلية)")
    parser.add_argument("--list", action="store_true", help="عرض كل المستخدمين والخروج")
    parser.add_argument("--create", action="store_true",
                        help="إنشاء المستخدم إن لم يكن موجوداً (يتطلب --role)")
    parser.add_argument("--role", choices=[r.value for r in Role], default=None,
                        help="دور المستخدم الجديد: admin | editor | writer")
    parser.add_argument("--display", default=None, help="الاسم الظاهر للمستخدم الجديد")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    app = create_app()

    if args.list:
        list_users(app)
        return 0

    if not args.username:
        username = pick_interactively(app)
        if not username:
            return 1
    else:
        username = args.username

    role = _role(args.role)
    if args.create and role is None:
        return 1

    while True:
        first = getpass.getpass("  كلمة المرور الجديدة: ")
        if len(first) < MIN_PASSWORD_LENGTH:
            print(f"  ✗ قصيرة — حد أدنى {MIN_PASSWORD_LENGTH} أحرف.")
            continue
        second = getpass.getpass("  أعد كلمة المرور: ")
        if first != second:
            print("  ✗ غير متطابقتين — أعد المحاولة.")
            continue
        password = first
        break

    if not change(app, username, password, display=args.display, role=role):
        return 1
    print("  ⚠ تأكد أن كلمات مرور التجربة (admin123…) لم تعد صالحة. احذف هذا الملف من الخادم إن أردت.")
    return 0


if __name__ == "__main__":
    sys.exit(main())