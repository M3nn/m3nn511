#!/usr/bin/env python3
"""يعبّي محتوى المنصة على الموقع الحيّ إن فرغت قاعدة بياناته.

يُشغّله مراقب GitHub Actions دوريًا، فلا يحتاج المستخدم أيّ تدخّل.

المتغيّرات:
  NASSR_BASE            عنوان الموقع (افتراضيًا نسخة Render).
  NASSR_ADMIN_USER      اسم مستخدم المسؤول.
  NASSR_ADMIN_PASSWORD  كلمة مرور المسؤول.

مكتوب بمكتبات بايثون القياسية فقط (بلا تثبيت أي حزمة).
آمن للتكرار: يتوقّف فورًا إن كان الموقع يحتوي أخبارًا منشورة.
"""
from __future__ import annotations

import datetime as dt
import http.cookiejar
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.getenv("NASSR_BASE", "https://nassr-news.onrender.com").rstrip("/")
USER = os.getenv("NASSR_ADMIN_USER", "").strip()
PASSWORD = os.getenv("NASSR_ADMIN_PASSWORD", "")
HERE = pathlib.Path(__file__).resolve().parent
CONTENT = json.loads((HERE / "content.json").read_text(encoding="utf-8"))

_cj = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_cj))
_opener.addheaders = [
    ("User-Agent", "nassr-reseed/1.0"),
    ("Accept-Language", "ar"),
]


def get(path: str) -> str:
    for attempt in range(3):
        try:
            with _opener.open(BASE + path, timeout=90) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001
            print(f"  ! GET {path} attempt={attempt + 1} err={exc}")
            time.sleep(5)
    return ""


def post(path: str, data: dict) -> bool:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("Referer", BASE + path)  # تشترطه حماية CSRF على HTTPS
    try:
        with _opener.open(req, timeout=90) as r:
            r.read()
        return True
    except urllib.error.HTTPError as exc:
        print(f"  ! POST {path} -> HTTP {exc.code}")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"  ! POST {path} err={exc}")
        return False


def csrf(html: str) -> str | None:
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    if not m:
        m = re.search(r'value="([^"]+)"[^>]*name="csrf_token"', html)
    return m.group(1) if m else None


def option_map(html: str) -> dict[str, int]:
    return {label.strip(): int(val) for val, label in
            re.findall(r'<option value="(\d+)"[^>]*>([^<]+)</option>', html)}


def login() -> bool:
    html = get("/auth/login")
    token = csrf(html)
    if not token:
        print("  ! login form not found")
        return False
    post("/auth/login", {
        "csrf_token": token,
        "username": USER,
        "password": PASSWORD,
    })
    editor = get("/editor/")
    return "لوحة التحرير" in editor


def seed() -> None:
    # --- التصنيفات ---
    for cat in CONTENT["categories"]:
        html = get("/admin/categories/new")
        post("/admin/categories/new", {
            "csrf_token": csrf(html),
            "name": cat["name"],
            "sort_order": str(cat["sort_order"]),
            "submit": "حفظ",
        })
    print(f"  categories ensured: {len(CONTENT['categories'])}")

    # --- خريطة الاسم -> المعرّف من نموذج المقال ---
    form = get("/editor/articles/new")
    cats = option_map(form)
    for cat in CONTENT["categories"]:
        print(f"    category id: {cat['name']} = {cats.get(cat['name'])}")

    # --- الأخبار ---
    made = 0
    for art in CONTENT["articles"]:
        form = get("/editor/articles/new")
        if post("/editor/articles/new", {
            "csrf_token": csrf(form),
            "title": art["title"],
            "body": art["body"],
            "summary": art["summary"],
            "category_id": str(cats.get(art["category"], 0)),
            "cover_image_url": "",
            "status": art["status"],
            "submit": "حفظ",
        }):
            made += 1
    print(f"  articles created: {made}/{len(CONTENT['articles'])}")

    # --- المهام ---
    form = get("/tasks/new")
    people = option_map(form)
    admin_id = 0
    for label, val in people.items():
        if "(مدير)" in label or "مدير" in label:
            admin_id = val
            break
    if not admin_id and people:
        admin_id = next(iter(people.values()))

    today = dt.date.today()
    tasks = 0
    for t in CONTENT["tasks"]:
        due = today + dt.timedelta(days=t["offset"] if t["offset"] > 0 else 0)
        form = get("/tasks/new")
        if post("/tasks/new", {
            "csrf_token": csrf(form),
            "title": t["title"],
            "description": "",
            "status": t["status"],
            "priority": t["priority"],
            "assignee_id": str(admin_id),
            "article_id": "0",
            "due_date": due.isoformat(),
        }):
            tasks += 1
    print(f"  tasks created: {tasks}/{len(CONTENT['tasks'])}")


def main() -> int:
    print(f"reseed: base={BASE} user={USER or '(none)'}")
    home = get("/")
    if not home:
        print("RESEED-SKIP: site unreachable (will retry next run).")
        return 0
    if "/article/" in home:
        print("RESEED-SKIP: content already present.")
        return 0

    print("RESEED: content missing -> filling the site.")
    if not USER or not PASSWORD:
        print("RESEED-FAIL: NASSR_ADMIN_USER / NASSR_ADMIN_PASSWORD not set.")
        return 0
    if not login():
        print("RESEED-FAIL: could not log in as admin.")
        return 0

    try:
        seed()
    except Exception as exc:  # noqa: BLE001
        print(f"RESEED-FAIL: {exc}")
        return 0

    after = get("/")
    ok = "/article/" in after
    print("RESEED-OK: site now has content." if ok
          else "RESEED-WARN: finished but no articles detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
