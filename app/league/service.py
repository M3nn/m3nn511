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
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import current_app, has_app_context
from hijridate import Gregorian

from app import AR_DAYS, AR_MONTHS, format_time_12

log = logging.getLogger("app.league")

RIYADH = timezone(timedelta(hours=3))
SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/ksa.1/scoreboard?dates={month}"
)
SUMMARY_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/ksa.1/summary?event={event}"
)
STANDINGS_URL = "https://site.api.espn.com/apis/v2/sports/soccer/ksa.1/standings"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"
CREST_DIR = Path(__file__).resolve().parent.parent / "static" / "img" / "teams"
PLAYERS_AR_FILE = Path(__file__).resolve().parent / "players_ar.json"
GOOGLE_TRANSLATE_URL = (
    "https://clients5.google.com/translate_a/t?client=dict-chrome-ex&sl=en&tl=ar&{q}"
)
MYMEMORY_URL = "https://api.mymemory.translated.net/get?q={q}&langpair=en|ar"
NAME_BATCH = 40             # عدد الأسماء في نداء ترجمة واحد
NAME_TRANSLATE_LIMIT = 120  # سقف الأسماء الجديدة المترجمة في التحديث الواحد
_AR_RE = re.compile(r"[\u0600-\u06FF]")

HIJRI_MONTHS = [
    "محرم", "صفر", "ربيع الأول", "ربيع الآخر", "جمادى الأولى", "جمادى الآخرة",
    "رجب", "شعبان", "رمضان", "شوال", "ذو القعدة", "ذو الحجة",
]

RESULTS_LIMIT = 6    # عدد النتائج المعروضة
FIXTURES_LIMIT = 10  # عدد المباريات القادمة المعروضة
FIXTURES_DAYS = 7    # نافذة «مباريات الأسبوع» بالأيام
SUMMARY_WORKERS = 8  # توازي جلب ملخصات ESPN
CARDS_LIMIT = 4      # أقصى عدد لاعبين بأوراق صفراء يُعرضون لكل فريق

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


# ------------------------------------------------------- أسماء اللاعبين بالعربية

_seed_names_cache: dict | None = None


def _read_name_file(path: Path | None) -> dict:
    if path is None:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_name_file(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8"
        )
    except OSError as exc:
        log.debug("league.names_write_failed err=%s", exc)


def _seed_names() -> dict:
    """قاموس الأسماء المرفق بالكود (إنجليزي ⇒ عربي)، يُقرأ مرة واحدة."""
    global _seed_names_cache
    if _seed_names_cache is None:
        _seed_names_cache = _read_name_file(PLAYERS_AR_FILE)
    return _seed_names_cache


def _names_cache_path() -> Path | None:
    """ملف ذاكرة الترجمة وقت التشغيل؛ None خارج سياق التطبيق (لا شبكة)."""
    try:
        folder = current_app.config.get("LEAGUE_CACHE_DIR") or current_app.instance_path
    except RuntimeError:
        return None
    return Path(folder) / "players_ar.json"


def _google_translate(chunk: list[str], timeout: float) -> dict:
    """ترجمة دفعة أسماء عبر نقطة جوجل العامة (نداء واحد لعدة أسماء)."""
    query = "&".join("q=" + urllib.parse.quote(name) for name in chunk)
    request = urllib.request.Request(
        GOOGLE_TRANSLATE_URL.format(q=query),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if isinstance(data, list) and data and isinstance(data[0], list):
        data = data[0]
    if not isinstance(data, list) or len(data) != len(chunk):
        return {}
    out: dict = {}
    for name, translated in zip(chunk, data):
        text = str(translated).strip()
        if text and _AR_RE.search(text):
            out[name] = text
    return out


def _mymemory_translate(name: str, timeout: float) -> str:
    request = urllib.request.Request(
        MYMEMORY_URL.format(q=urllib.parse.quote(name)),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = str((data.get("responseData") or {}).get("translatedText") or "").strip()
    if not text or not _AR_RE.search(text) or "MYMEMORY WARNING" in text.upper():
        return ""
    return re.split(r"[(,،]", text)[0].strip()  # إزالة أي شرح قاموسي


def translate_names(names: list[str]) -> dict:
    """أسماء إنجليزية ⇒ عربية. جوجل أولاً ثم MyMemory احتياطاً.

    **نقطة الاستبدال في الاختبارات:** يستبدلها ``monkeypatch`` فلا توجد شبكة."""
    translated: dict = {}
    timeout = float(current_app.config["LEAGUE_TIMEOUT"])
    for start in range(0, len(names), NAME_BATCH):
        chunk = names[start:start + NAME_BATCH]
        try:
            translated.update(_google_translate(chunk, timeout))
        except Exception as exc:
            log.debug("league.name_batch_failed err=%s", exc)
    missing = [n for n in names if n not in translated]
    for name in missing[:NAME_TRANSLATE_LIMIT]:
        try:
            text = _mymemory_translate(name, timeout)
        except Exception as exc:
            log.debug("league.name_fallback_failed err=%s", exc)
            continue
        if text:
            translated[name] = text
    return translated


def _arabic_names(names: set) -> dict:
    """خريطة الاسم الإنجليزي ⇒ عربي من القاموس المرفق + ذاكرة وقت التشغيل،
    ويُترجم الجديد منها فقط ثم يُخزَّن. تعذّر الشبكة يُبقي الاسم الإنجليزي."""
    wanted = {str(n).strip() for n in names if n and str(n).strip()}
    if not wanted:
        return {}
    mapping = dict(_seed_names())
    path = _names_cache_path()
    runtime = _read_name_file(path)
    mapping.update(runtime)
    missing = sorted(n for n in wanted if n not in mapping)
    if missing and path is not None:
        try:
            fresh = translate_names(missing[:NAME_TRANSLATE_LIMIT])
        except Exception as exc:
            log.debug("league.names_translate_failed err=%s", exc)
            fresh = {}
        if fresh:
            mapping.update(fresh)
            runtime.update(fresh)
            _write_name_file(path, runtime)
    return {n: mapping.get(n, n) for n in wanted}


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


def fetch_summary(event_id: str) -> dict:
    """ملخص مباراة (أحداث/بطاقات/تبديلات) من ESPN.

    **نقطة الاستبدال في الاختبارات:** يستبدلها ``monkeypatch`` فلا توجد شبكة."""
    timeout = float(current_app.config["LEAGUE_TIMEOUT"])
    return _http_get_json(SUMMARY_URL.format(event=event_id), timeout)


def fetch_standings() -> dict:
    """جدول ترتيب دوري روشن (كل الفرق) في نداء واحد.

    **نقطة الاستبدال في الاختبارات:** يستبدلها ``monkeypatch`` فلا توجد شبكة."""
    timeout = float(current_app.config["LEAGUE_TIMEOUT"])
    return _http_get_json(STANDINGS_URL, timeout)


def _fetch_many(event_ids: list[str]) -> dict:
    """ملخصات عدة مباريات بالتوازي: ``{id: summary}`` مع تجاهل الفاشلة.

    تعمل داخل وخارج سياق التطبيق: تفتح سياق Flask لكل عامل (سياق التطبيق لا
    يُورَّث للخيوط)."""
    if not event_ids:
        return {}
    app = current_app._get_current_object() if has_app_context() else None
    collected: dict = {}

    def one(event_id: str):
        def do():
            return event_id, fetch_summary(event_id)

        try:
            if app is None:
                return do()
            with app.app_context():
                return do()
        except Exception as exc:  # مباراة واحدة لا تُسقط البقية
            log.debug("league.summary_failed id=%s err=%s", event_id, exc)
            return event_id, None

    with ThreadPoolExecutor(max_workers=SUMMARY_WORKERS) as pool:
        for event_id, data in pool.map(one, event_ids):
            if data:
                collected[event_id] = data
    return collected


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


def _team_label(team: dict | None) -> str:
    """اسم الفريق بالعربية من كائن الفريق (بالاعتماد على معرّف ESPN)."""
    team = team or {}
    team_id = str(team.get("id") or "")
    return TEAMS_AR.get(team_id) or str(team.get("displayName") or "").strip()


def _assists_from_rosters(summary: dict) -> list[dict]:
    """لاعبو المباراة الذين صنعوا أهدافاً (إجمالي التمريرات الحاسمة لكل لاعب)."""
    assists: list[dict] = []
    for block in summary.get("rosters") or []:
        team = _team_label(block.get("team"))
        for player in block.get("roster") or []:
            total = 0.0
            for stat in player.get("stats") or []:
                if stat.get("name") == "goalAssists":
                    try:
                        total = float(stat.get("value") or 0)
                    except (TypeError, ValueError):
                        total = 0.0
            name = str((player.get("athlete") or {}).get("displayName") or "").strip()
            if total > 0 and name:
                assists.append({"player": name, "team": team, "count": int(total)})
    return assists


def _summary_view(summary: dict) -> dict | None:
    """يحوّل ملخص ESPN إلى بنية جاهزة لتلميح المباراة (بلا HTML)، أو None للفراغ.

    الأحداث المدعومة: الأهداف (بما فيها الجزاء والعكسي)، البطاقات (أصفر/أحمر)،
    التبديلات (الداخل/الخارج بالدقيقة)، وقائمة صنّاع الأهداف من إحصاء اللاعبين."""
    goals: list[dict] = []
    cards: list[dict] = []
    subs: list[dict] = []
    for event in summary.get("keyEvents") or []:
        etype = str((event.get("type") or {}).get("type") or "")
        minute = str((event.get("clock") or {}).get("displayValue") or "").strip()
        team = _team_label(event.get("team"))
        names = [
            str((p.get("athlete") or {}).get("displayName") or "").strip()
            for p in event.get("participants") or []
        ]
        player = names[0] if names else ""
        if "own" in etype and "goal" in etype:
            goals.append({"minute": minute, "player": player, "team": team, "kind": "own"})
        elif etype == "penalty---scored":
            goals.append({"minute": minute, "player": player, "team": team, "kind": "penalty"})
        elif etype == "goal":
            goals.append({"minute": minute, "player": player, "team": team, "kind": "goal"})
        elif "red" in etype:
            cards.append({"minute": minute, "player": player, "team": team, "kind": "red"})
        elif "yellow" in etype:
            cards.append({"minute": minute, "player": player, "team": team, "kind": "yellow"})
        elif etype == "substitution":
            subs.append({
                "minute": minute,
                "team": team,
                "in": player,
                "out": names[1] if len(names) > 1 else "",
            })

    assists = _assists_from_rosters(summary)
    if not (goals or cards or subs or assists):
        return None
    return {"goals": goals, "cards": cards, "subs": subs, "assists": assists}


def _view_names(view: dict) -> set:
    """كل أسماء اللاعبين الواردة في ملخص مباراة."""
    names = set()
    for goal in view.get("goals", []):
        names.add(goal.get("player", ""))
    for card in view.get("cards", []):
        names.add(card.get("player", ""))
    for sub in view.get("subs", []):
        names.add(sub.get("in", ""))
        names.add(sub.get("out", ""))
    for assist in view.get("assists", []):
        names.add(assist.get("player", ""))
    return {n for n in names if n}


def _translate_view(view: dict, names: dict) -> None:
    """يستبدل أسماء اللاعبين بنسخها العربية داخل الملخص (في المكان)."""
    def arabic(value: str | None) -> str | None:
        return names.get(value, value) if value else value

    for goal in view.get("goals", []):
        goal["player"] = arabic(goal.get("player"))
    for card in view.get("cards", []):
        card["player"] = arabic(card.get("player"))
    for sub in view.get("subs", []):
        sub["in"] = arabic(sub.get("in"))
        sub["out"] = arabic(sub.get("out"))
    for assist in view.get("assists", []):
        assist["player"] = arabic(assist.get("player"))


# -------------------------------------------- معاينة المباريات القادمة

def _cards_path() -> Path:
    folder = current_app.config.get("LEAGUE_CACHE_DIR") or current_app.instance_path
    return Path(folder) / "cards.json"


def _read_cards(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_cards(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        log.debug("league.cards_write_failed err=%s", exc)


def _card_table(all_results: list[dict]) -> dict:
    """جدول بطاقات اللاعبين (أصفر/أحمر) من كل مباريات النافذة المنتهية.

    مفتاح كل لاعب هو اسمه الإنجليزي، ويُترجم لاحقاً عند بناء المعاينة. يُحسب
    مرّة واحدة ويُخزَّن حتى تتغيّر قائمة المباريات المنتهية (لا نُثقل ESPN).
    لا يُعاد استخدام كاش لم يُبنَ بنجاح (علامة ``ok``)."""
    ids = [str(m["id"]) for m in all_results]
    empty = {"ok": True, "ids": [], "players": {}, "last_match": {}}
    if not ids:
        return empty
    path = _cards_path()
    cached = _read_cards(path)
    if (
        cached.get("ok")
        and cached.get("ids") == ids
        and isinstance(cached.get("players"), dict)
    ):
        return cached

    last_match: dict = {}  # team_id ⇒ معرّف آخر مباراة منتهية له
    for match in sorted(all_results, key=lambda m: m["kickoff"]):
        for side in ("home", "away"):
            last_match[str(match[side]["id"])] = str(match["id"])

    players: dict = {}
    for event_id, summary in _fetch_many(ids).items():
        for event in summary.get("keyEvents") or []:
            etype = str((event.get("type") or {}).get("type") or "")
            kind = "red" if "red" in etype else ("yellow" if "yellow" in etype else "")
            if not kind:
                continue
            team_id = str((event.get("team") or {}).get("id") or "")
            for participant in event.get("participants") or []:
                name = str((participant.get("athlete") or {}).get("displayName") or "").strip()
                if not name:
                    continue
                record = players.setdefault(
                    name, {"team_id": team_id, "yellow": 0, "red": 0, "red_matches": []}
                )
                record["team_id"] = team_id
                if kind == "red":
                    record["red"] += 1
                    record["red_matches"].append(event_id)
                else:
                    record["yellow"] += 1

    table = {"ok": True, "ids": ids, "players": players, "last_match": last_match}
    _write_cards(path, table)
    return table


def _team_cards(team_id: str, table: dict) -> dict:
    """الموقوفون (طرد في آخر مباراة) وأصحاب الإنذارات لفريق واحد."""
    suspended: list[str] = []
    yellows: list[dict] = []
    last_match = (table.get("last_match") or {}).get(team_id)
    for name, record in (table.get("players") or {}).items():
        if str(record.get("team_id") or "") != team_id:
            continue
        if last_match and last_match in (record.get("red_matches") or []):
            suspended.append(name)
        if record.get("yellow"):
            yellows.append({"name": name, "count": int(record["yellow"])})
    yellows.sort(key=lambda item: item["count"], reverse=True)
    return {"suspended": suspended, "yellow": yellows[:CARDS_LIMIT]}


def _standings_map(data: dict) -> dict:
    """``{team_id: {rank, points, played, record, gd}}`` من ردّ ترتيب ESPN
    (يدعم ردّ الترتيب المستقل وردّ ملخص المباراة معاً)."""
    entries: list = []
    children = data.get("children")
    if isinstance(children, list) and children:
        entries = ((children[0].get("standings") or {}).get("entries")) or []
    if not entries:
        groups = (data.get("standings") or {}).get("groups")
        if isinstance(groups, list) and groups:
            entries = ((groups[0].get("standings") or {}).get("entries")) or []
    out: dict = {}
    for entry in entries:
        team = entry.get("team")
        team_id = str(entry.get("id") or "")
        if not team_id and isinstance(team, dict):
            team_id = str(team.get("id") or "")
        if not team_id:
            continue
        stats = {s.get("name"): s.get("displayValue") for s in entry.get("stats") or []}
        out[team_id] = {
            "rank": stats.get("rank"),
            "points": stats.get("points"),
            "played": stats.get("gamesPlayed"),
            "record": stats.get("overall"),
            "gd": stats.get("pointDifferential"),
        }
    return out


def _forms(summary: dict) -> dict:
    """سلسلة النتائج لآخر مباريات كل فريق مثل ``WWLDL`` (الأحدث أولاً)."""
    comp = ((summary.get("header") or {}).get("competitions") or [{}])[0]
    out: dict = {}
    for rival in comp.get("competitors") or []:
        team_id = str((rival.get("team") or {}).get("id") or "")
        if team_id:
            out[team_id] = str(rival.get("form") or "")
    return out


def _leaders(summary: dict) -> dict:
    """هداف وصانع أهداف كل فريق من ``leaders``."""
    out: dict = {}
    for block in summary.get("leaders") or []:
        team_id = str((block.get("team") or {}).get("id") or "")
        if not team_id:
            continue
        categories = {c.get("name"): c for c in block.get("leaders") or []}

        def top(category_name: str):
            leaders = (categories.get(category_name) or {}).get("leaders") or []
            if not leaders:
                return None
            leader = leaders[0]
            name = str((leader.get("athlete") or {}).get("displayName") or "").strip()
            value = (leader.get("mainStat") or {}).get("value")
            if not name or value in (None, ""):
                return None
            try:
                value = int(float(value))
            except (TypeError, ValueError):
                value = str(value)
            return {"name": name, "value": value}

        out[team_id] = {"scorer": top("goalsLeaders"), "assist": top("assistsLeaders")}
    return out


def _short_date(value: str) -> str:
    """تاريخ مختصر بالعربية: ``2026-08-28T18:00Z`` ⇒ «28 أغسطس»."""
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(RIYADH)
    except (TypeError, ValueError):
        return value
    return f"{moment.day} {AR_MONTHS[moment.month - 1]}"


def _h2h(series: list, team_names: dict) -> dict | None:
    """آخر المواجهات المباشرة (حتى 3) مع الأسماء العربية والنتائج."""
    if not series:
        return None
    block = series[0]
    events: list[dict] = []
    for event in (block.get("events") or [])[:3]:
        rivals = {r.get("homeAway"): r for r in event.get("competitors") or []}
        home, away = rivals.get("home") or {}, rivals.get("away") or {}
        home_team = home.get("team") or {}
        away_team = away.get("team") or {}
        home_id = str(home_team.get("id") or "")
        away_id = str(away_team.get("id") or "")
        events.append({
            "date": _short_date(str(event.get("date") or "")),
            "home": team_names.get(home_id) or str(home_team.get("displayName") or ""),
            "away": team_names.get(away_id) or str(away_team.get("displayName") or ""),
            "home_score": "" if home.get("score") is None else str(home.get("score")),
            "away_score": "" if away.get("score") is None else str(away.get("score")),
        })
    if not events:
        return None
    return {"events": events}


def _probabilities(odds: list) -> dict | None:
    """احتمالات الفوز من أسعار المُراهنة (تُطبَّع إلى 100%)."""
    if not odds:
        return None
    book = odds[0]

    def implied(money_line):
        try:
            money_line = float(money_line)
        except (TypeError, ValueError):
            return None
        if money_line > 0:
            return 100.0 / (money_line + 100.0)
        return (-money_line) / ((-money_line) + 100.0)

    home = implied((book.get("homeTeamOdds") or {}).get("moneyLine"))
    away = implied((book.get("awayTeamOdds") or {}).get("moneyLine"))
    draw = implied((book.get("drawOdds") or {}).get("moneyLine"))
    if home is None or away is None:
        return None
    total = home + away + (draw or 0.0)
    if total <= 0:
        return None
    out = {"home": round(home / total * 100), "away": round(away / total * 100)}
    if draw is not None:
        out["draw"] = round(draw / total * 100)
    return out


def _preview_view(match: dict, summary: dict, standings: dict,
                  team_names: dict, cards_table: dict) -> dict:
    """يبني معاينة المباراة القادمة من ملخص ESPN + الترتيب + جدول البطاقات."""
    home_id = str(match["home"]["id"])
    away_id = str(match["away"]["id"])
    forms = _forms(summary) if summary else {}
    leaders = _leaders(summary) if summary else {}
    return {
        "standings": {"home": standings.get(home_id), "away": standings.get(away_id)},
        "form": {"home": forms.get(home_id, ""), "away": forms.get(away_id, "")},
        "h2h": _h2h(summary.get("seasonseries") if summary else None, team_names),
        "leaders": {"home": leaders.get(home_id), "away": leaders.get(away_id)},
        "cards": {
            "home": _team_cards(home_id, cards_table),
            "away": _team_cards(away_id, cards_table),
        },
        "odds": _probabilities(summary.get("odds") if summary else None),
    }


def _preview_names(preview: dict) -> set:
    """أسماء اللاعبين الواردة في معاينة (هدافون/صنّاع/بطاقات) لترجمتها."""
    names: set = set()
    for side in ("home", "away"):
        leader = (preview.get("leaders") or {}).get(side) or {}
        for key in ("scorer", "assist"):
            item = leader.get(key)
            if item and item.get("name"):
                names.add(item["name"])
        cards = (preview.get("cards") or {}).get(side) or {}
        names.update(cards.get("suspended") or [])
        for item in cards.get("yellow") or []:
            if item.get("name"):
                names.add(item["name"])
    return {n for n in names if n}


def _translate_preview(preview: dict, names: dict) -> None:
    """يستبدل أسماء لاعبي المعاينة بنسخها العربية (في المكان)."""
    def arabic(value):
        return names.get(value, value) if value else value

    for side in ("home", "away"):
        leader = (preview.get("leaders") or {}).get(side) or {}
        for key in ("scorer", "assist"):
            item = leader.get(key)
            if item and item.get("name"):
                item["name"] = arabic(item["name"])
        cards = (preview.get("cards") or {}).get(side) or {}
        cards["suspended"] = [arabic(n) for n in cards.get("suspended") or []]
        for item in cards.get("yellow") or []:
            item["name"] = arabic(item.get("name"))


def _attach_previews(payload: dict) -> dict:
    """يلحق بكل مباراة قادمة معاينة: الترتيب، الحالة، المواجهات، الهدافون،
    الغيابات/البطاقات، واحتمالات الفوز. تعذّر أي جزء لا يُسقط البقية."""
    fixtures = payload.get("fixtures") or []
    if not fixtures:
        return payload
    all_results = payload.get("all_results") or []

    team_names: dict = {}
    for match in list(all_results) + list(fixtures):
        for side in ("home", "away"):
            team_names[str(match[side]["id"])] = match[side]["name"]

    try:
        standings = _standings_map(fetch_standings())
    except Exception as exc:
        log.debug("league.standings_failed err=%s", exc)
        standings = {}

    try:
        cards_table = _card_table(all_results)
    except Exception as exc:
        log.debug("league.cards_failed err=%s", exc)
        cards_table = {"players": {}, "last_match": {}}

    summaries = _fetch_many([str(m["id"]) for m in fixtures])

    placed: list[tuple[dict, dict]] = []
    names: set = set()
    for match in fixtures:
        preview = _preview_view(
            match, summaries.get(str(match["id"])) or {}, standings, team_names, cards_table
        )
        placed.append((match, preview))
        names |= _preview_names(preview)

    translated = _arabic_names(names)
    for match, preview in placed:
        _translate_preview(preview, translated)
        match["preview"] = preview
    return payload



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
        "all_results": results,  # كل المنتهية (لحساب البطاقات) لا المعروضة فقط
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


def _attach_summaries(payload: dict) -> dict:
    """يلحق ملخص الأحداث بالمباريات المنتهية المعروضة بعد ترجمة أسماء اللاعبين.
    فشل مباراة أو تعذّر الترجمة لا يُسقط البقية."""
    results = payload.get("results") or []
    summaries = _fetch_many([str(m["id"]) for m in results])
    placed: list[tuple[dict, dict]] = []
    names: set = set()
    for match in results:
        summary = summaries.get(str(match["id"]))
        if not summary:
            continue
        view = _summary_view(summary)
        if not view:
            continue
        placed.append((match, view))
        names |= _view_names(view)

    translated = _arabic_names(names)
    for match, view in placed:
        _translate_view(view, translated)
        match["summary"] = view
    return payload


def _refresh(old: dict | None, now: datetime) -> dict | None:
    """يجلب ويبني ويخزّن؛ عند أي فشل يعود بالنسخة القديمة (أو None)."""
    try:
        events = fetch_scoreboards(now)
        payload = build_payload(events, now)
        _attach_summaries(payload)
        _attach_previews(payload)
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
