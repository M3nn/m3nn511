"""دوري روشن السعودي: مواعيد المباريات وآخر النتائج لصفحة الرئيسية.

المصدر: واجهة ESPN العامة ``site.api.espn.com`` لدوري ``ksa.1`` — بلا مفتاح API.
التدفق:

1. ``fetch_scoreboards()`` — طلبات شهرية (الشهر السابق/الحالي/القادم) بهوية
   متصفّح، مع تنزيل أي شعار فريق مفقود محلياً.
2. ``build_payload()`` — تطبيع الأحداث: أسماء عربية، ملعب ومدينة بالعربية،
   توقيت الرياض، تاريخ ميلادي وهجري، نتيجة أو موعد.
3. ``get_league()`` — يقرأ الكاش؛ يجدّده إن جاوز ``LEAGUE_TTL``، ويحتفظ
   بالنسخة القديمة عند تعذّر الشبكة، ويُخفي القسم تماماً إن لم تكن هناك بيانات.

لا نداء شبكة في الاختبارات: ``TestConfig.LEAGUE_ENABLED = False``، والاختبارات
التي تحتاج القسم تستبدل ``fetch_scoreboards`` ببيانات مُعلّمة.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import current_app
from hijridate import Gregorian

from app import AR_DAYS, AR_MONTHS, format_time_12

log = logging.getLogger("app.league")

RIYADH = timezone(timedelta(hours=3))
SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/ksa.1/scoreboard?dates={month}"
)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"
CREST_DIR = Path(__file__).resolve().parent.parent / "static" / "img" / "teams"

HIJRI_MONTHS = [
    "محرم", "صفر", "ربيع الأول", "ربيع الآخر", "جمادى الأولى", "جمادى الآخرة",
    "رجب", "شعبان", "رمضان", "شوال", "ذو القعدة", "ذو الحجة",
]

RESULTS_LIMIT = 6    # عدد النتائج المعروضة
FIXTURES_LIMIT = 10  # عدد المباريات القادمة المعروضة
FIXTURES_DAYS = 7    # نافذة «مباريات الأسبوع» بالأيام

# أسماء الأندية بالعربية — المفتاح معرّف الفريق في ESPN
TEAMS_AR = {
    "929": "الهلال",
    "817": "النصر",
    "8346": "الأهلي",
    "2276": "الاتحاد",
    "793": "الشباب",
    "8363": "الاتفاق",
    "22022": "القادسية",
    "18459": "التعاون",
    "13033": "الفتح",
    "21446": "الفيصلي",
    "21827": "الفيحاء",
    "21829": "الخليج",
    "21833": "أبها",
    "21964": "الحزم",
    "21965": "الرياض",
    "22028": "الخلود",
    "130899": "نيوم",
    "131746": "الدرعية",
}

# الملاعب: الاسم الإنجليزي ← (الاسم بالعربية، المدينة بالعربية)
VENUES_AR = {
    "Al Ettifaq Club Stadium": ("ملعب نادي الاتفاق", "الدمام"),
    "Al Fateh Club Stadium": ("ملعب نادي الفتح", "الهفوف"),
    "Al Majma'a Sport City Stadium": ("ملعب مدينة المجمعة الرياضية", "المجمعة"),
    "Al Taawon Club Stadium": ("ملعب نادي التعاون", "بريدة"),
    "Al-Hazm Club Stadium": ("ملعب نادي الحزم", "الرس"),
    "Al-Shabab Club Stadium": ("ملعب نادي الشباب", "الرياض"),
    "Al-Awwal Park": ("ملعب الأول بارك", "الرياض"),
    "Damac Club Stadium": ("ملعب نادي ضمك", "خميس مشيط"),
    "Damac Stadium": ("ملعب نادي ضمك", "خميس مشيط"),
    "King Abdullah Sports City": ("ملعب الملك عبدالله الرياضية", "جدة"),
    "King Khalid Sport City Stadium": ("ملعب الملك خالد الرياضية", "تبوك"),
    "Kingdom Arena": ("أرضية المملكة أرينا", "الرياض"),
    "Prince Abdullah Al-Faisal Stadium": ("ملعب الأمير عبدالله الفيصل", "جدة"),
    "Prince Faisal bin Fahd Stadium": ("ملعب الأمير فيصل بن فهد", "الرياض"),
    "Prince Mohammed Bin Fahd Stadium": ("ملعب الأمير محمد بن فهد", "الدمام"),
    "Prince Sultan bin Abdulaziz Sports City Stadium": (
        "ملعب الأمير سلطان بن عبدالعزيز الرياضية",
        "أبها",
    ),
}

# احتياطي: مدينة إنجليزية تظهر وحدها حين يغيب الاسم الرسمي للملعب
CITY_AR = {
    "King Fahd International Stadium": "الرياض",
    "Riyadh": "الرياض",
    "Dammam": "الدمام",
    "Jeddah": "جدة",
    "Tabuk": "تبوك",
    "Abha": "أبها",
    "Buraidah": "بريدة",
    "Al-Hofuf": "الهفوف",
    "Al Majma'ah": "المجمعة",
    "Al-Rass": "الرس",
}


# ---------------------------------------------------------------- القراءة

def _cache_path() -> Path:
    folder = current_app.config.get("LEAGUE_CACHE_DIR") or current_app.instance_path
    return Path(folder) / "league.json"


def _read_cache(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or "fetched_at" not in payload:
        return None
    return payload


def _write_cache(path: Path, payload: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        log.warning("league.cache_write_failed err=%s", exc)


def _age_seconds(payload: dict, now: datetime) -> float:
    try:
        fetched = datetime.fromisoformat(payload["fetched_at"])
    except (KeyError, TypeError, ValueError):
        return float("inf")
    return (now - fetched).total_seconds()


# ---------------------------------------------------------------- الجلب

def _http_get_json(url: str, timeout: float) -> dict:
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _months_window(now: datetime) -> list[str]:
    """أشهر تغطي [now − 14 يوماً، now + 8 أيام] بصيغة ESPN ``YYYYMM``."""
    start = (now - timedelta(days=14)).replace(day=1)
    end = now + timedelta(days=8)
    months: list[str] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(f"{year:04d}{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return months


def _ensure_crests(events: list[dict]) -> None:
    """ينزّل شعار كل فريق مفقود. فشل التنزيل لا يُسقط تحديث البيانات."""
    try:
        CREST_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    for ev in events:
        comp = (ev.get("competitions") or [{}])[0]
        for rival in comp.get("competitors") or []:
            team = rival.get("team") or {}
            team_id, logo_url = str(team.get("id") or ""), team.get("logo")
            if not team_id or not logo_url:
                continue
            target = CREST_DIR / f"{team_id}.png"
            if target.exists():
                continue
            try:
                req = urllib.request.Request(
                    logo_url, headers={"User-Agent": USER_AGENT}
                )
                with urllib.request.urlopen(req, timeout=6) as resp:
                    target.write_bytes(resp.read())
                log.info("league.crest_saved team=%s", team_id)
            except Exception as exc:  # الشعار ترفاق لا شرط
                log.debug("league.crest_failed team=%s err=%s", team_id, exc)


def fetch_scoreboards(now: datetime) -> list[dict]:
    """أحداث الأشهر المطلوبة. فشل شهر واحد يستمرّ بالبقية.

    **نقطة الاستبدال في الاختبارات:** يستبدلها ``monkeypatch`` فلا توجد شبكة."""
    timeout = float(current_app.config["LEAGUE_TIMEOUT"])
    events: list[dict] = []
    for month in _months_window(now):
        try:
            data = _http_get_json(SCOREBOARD_URL.format(month=month), timeout)
        except Exception as exc:
            log.warning("league.fetch_failed month=%s err=%s", month, exc)
            continue
        events.extend(data.get("events") or [])
    _ensure_crests(events)
    return events


# ---------------------------------------------------------------- التطبيع

def _crest_name(team_id: str) -> str | None:
    for name in (f"{team_id}.png", f"{team_id}.svg"):
        if (CREST_DIR / name).exists():
            return name
    return None


def _team(rival: dict) -> dict:
    team = rival.get("team") or {}
    team_id = str(team.get("id") or "")
    return {
        "id": team_id,
        "name": TEAMS_AR.get(team_id) or team.get("displayName") or "—",
        "crest": _crest_name(team_id),
    }


def _hijri_label(day) -> str:
    """التاريخ الهجري (أم القرى) بالعربية: «28 ربيع الآخر 1448»."""
    hijri = Gregorian(day.year, day.month, day.day).to_hijri()
    return f"{hijri.day} {HIJRI_MONTHS[hijri.month - 1]} {hijri.year}"


def _match(event: dict) -> dict | None:
    """يحوّل حدث ESPN إلى بطاقة مباراة، أو يرجع None للحدث الناقص."""
    competitions = event.get("competitions") or []
    if not competitions:
        return None
    comp = competitions[0]
    rivals = {r.get("homeAway"): r for r in comp.get("competitors") or []}
    if "home" not in rivals or "away" not in rivals:
        return None

    kickoff = datetime.fromisoformat(
        str(event["date"]).replace("Z", "+00:00")
    ).astimezone(RIYADH)

    venue = comp.get("venue") or {}
    stadium_en = str(venue.get("fullName") or "").strip()
    city_en = str((venue.get("address") or {}).get("city") or "").strip()
    stadium, city = VENUES_AR.get(
        stadium_en, (stadium_en, CITY_AR.get(city_en, city_en))
    )

    state = ((event.get("status") or {}).get("type") or {}).get("state", "pre")
    status = {"post": "finished", "in": "live"}.get(state, "scheduled")

    return {
        "id": str(event.get("id") or ""),
        "status": status,
        "kickoff": kickoff.replace(microsecond=0).isoformat(),
        "weekday": AR_DAYS[kickoff.weekday()],
        "date_greg": f"{kickoff.day} {AR_MONTHS[kickoff.month - 1]} {kickoff.year}",
        "time": format_time_12(kickoff.hour, kickoff.minute),
        "date_hijri": _hijri_label(kickoff.date()),
        "stadium": stadium,
        "city": city,
        "home": _team(rivals["home"]),
        "away": _team(rivals["away"]),
        "home_score": int(rivals["home"].get("score") or 0),
        "away_score": int(rivals["away"].get("score") or 0),
    }


def _dedupe(matches: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique = []
    for match in matches:
        if match["id"] in seen:
            continue
        seen.add(match["id"])
        unique.append(match)
    return unique


def build_payload(events: list[dict], now: datetime) -> dict:
    """ينظّف الأحداث إلى قائمتي النتائج والمواعيد مع التاريخ الميلادي والهجري."""
    results: list[dict] = []
    fixtures: list[dict] = []
    for event in events:
        try:
            match = _match(event)
        except Exception as exc:  # حدث تالف واحد لا يُسقط الدفعة كلها
            log.debug("league.bad_event id=%s err=%s", event.get("id"), exc)
            continue
        if match is None:
            continue
        if match["status"] == "finished":
            results.append(match)
        else:
            fixtures.append(match)

    results = _dedupe(sorted(results, key=lambda m: m["kickoff"], reverse=True))
    fixtures = _dedupe(sorted(fixtures, key=lambda m: m["kickoff"]))
    return {
        "fetched_at": now.replace(microsecond=0).isoformat(),
        "updated": (
            f"{now.day} {AR_MONTHS[now.month - 1]} {now.year} - "
            f"{format_time_12(now.hour, now.minute)}"
        ),
        "results": results[:RESULTS_LIMIT],
        "fixtures": fixtures[:FIXTURES_LIMIT],
    }


# ---------------------------------------------------------------- العرض

def _visible(payload: dict, now: datetime) -> dict | None:
    """يقصّ المباريات القادمة إلى «هذا الأسبوع» حسب وقت القراءة لا وقت الكاش:
    من قبل ثلاث ساعات حتى نهاية الأسبوع الحالي (صباح الاثنين القادم).
    الحدّ عند نهاية الأسبوع (لا +7 أيام) يمنع تسرّب مباراة من الجولة التالية."""
    week_end = _week_end(now)
    lower = (now - timedelta(hours=3)).isoformat()
    upper = week_end.isoformat()
    fixtures = [
        m for m in payload.get("fixtures", []) if lower <= m.get("kickoff", "") <= upper
    ]
    results = payload.get("results", [])[:RESULTS_LIMIT]
    if not fixtures and not results:
        return None
    return {**payload, "fixtures": fixtures, "results": results}


def _week_end(now: datetime) -> datetime:
    """صباح الاثنين القادم بتوقيت الرياض = نهاية الأسبوع الحالي."""
    days = 7 - now.weekday()  # الاثنين=0 … الأحد=6؛ الاثنين تعني أسبوعاً كاملاً
    return (now + timedelta(days=days)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def _refresh(old: dict | None, now: datetime) -> dict | None:
    """يجلب ويبني ويخزّن؛ عند أي فشل يعود بالنسخة القديمة (أو None)."""
    try:
        events = fetch_scoreboards(now)
        payload = build_payload(events, now)
    except Exception as exc:
        log.warning("league.refresh_failed err=%s", exc)
        return old
    if not payload["results"] and not payload["fixtures"]:
        log.warning("league.refresh_empty events=%s", len(events))
        return old
    _write_cache(_cache_path(), payload)
    log.info(
        "league.refreshed results=%s fixtures=%s",
        len(payload["results"]),
        len(payload["fixtures"]),
    )
    return payload


def get_league() -> dict | None:
    """نقطة الدخول للقوالب: بيانات مرئية، أو None لإخفاء القسم."""
    if not current_app.config.get("LEAGUE_ENABLED"):
        return None
    now = datetime.now(RIYADH).replace(microsecond=0)
    cache = _cache_path()
    payload = _read_cache(cache)
    ttl = int(current_app.config["LEAGUE_TTL"])
    if payload is None or _age_seconds(payload, now) > ttl:
        payload = _refresh(payload, now)
    if payload is None:
        return None
    return _visible(payload, now)


def refresh() -> dict | None:
    """تحديث إجباري متجاهل المهلة — للأمر ``flask fetch-league``."""
    now = datetime.now(RIYADH).replace(microsecond=0)
    return _refresh(_read_cache(_cache_path()), now)
