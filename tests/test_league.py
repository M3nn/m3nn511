"""قسم دوري روشن في الرئيسية: بلا شبكة، بتاريخ ميلادي وهجري، ويُخفى عند الفشل.

مصدر البيانات ``fetch_scoreboards`` يُستبدل دائماً ببيانات مُعلّمة، والكاش في
مجلد مؤقّت — أي نداء شبكة حقيقي هنا يُفشل الاختبار برسالة صريحة.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.league import service
from app.extensions import db
from app.models import Article, ArticleStatus


def _rival(team_id: str, home_away: str, score: int = 0) -> dict:
    return {
        "homeAway": home_away,
        "score": score,
        "team": {
            "id": team_id,
            "displayName": f"Team {team_id}",
            "logo": f"https://example.invalid/{team_id}.png",
        },
    }


def _event(
    event_id: str,
    utc: str,
    state: str,
    home: str,
    away: str,
    home_score: int = 0,
    away_score: int = 0,
    stadium: str = "",
    city: str = "",
) -> dict:
    """حدث بالشكل الذي يعيده ESPN (التاريخ بـ UTC بصيغة ``YYYY-MM-DDTHH:MMZ``)."""
    return {
        "id": event_id,
        "date": utc,
        "status": {"type": {"state": state}},
        "competitions": [
            {
                "competitors": [_rival(home, "home", home_score), _rival(away, "away", away_score)],
                "venue": {"fullName": stadium, "address": {"city": city}},
            }
        ],
    }


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


@pytest.fixture()
def league(app, tmp_path, monkeypatch):
    """يشعل القسم: كاش معزول + شعارات مصطنعة + مصدر مُعلَّم بلا شبكة."""
    app.config["LEAGUE_ENABLED"] = True
    app.config["LEAGUE_CACHE_DIR"] = str(tmp_path / "cache")

    crests = tmp_path / "crests"
    crests.mkdir()
    for team_id in ("929", "817", "8346", "2276"):
        (crests / f"{team_id}.png").write_bytes(b"png-bytes")
    monkeypatch.setattr(service, "CREST_DIR", crests)
    monkeypatch.setattr(service, "fetch_scoreboards", lambda now: [])
    monkeypatch.setattr(service, "fetch_summary", lambda event_id: {})
    return app


def test_section_is_hidden_when_disabled(client):
    """الإعداد الافتراضي في الاختبارات: لا قسم ولا أي نداء شبكة."""
    res = client.get("/")
    html = res.get_data(as_text=True)
    assert res.status_code == 200
    assert "دوري روشن" not in html


def test_home_renders_fixtures_results_and_venue_details(league, monkeypatch, article, users, category):
    # خبر ثانٍ كي تظهر شبكة «أحدث الأخبار» في وسط الساحة
    second = Article(
        title="النصر يستعد لمباراة الجولة القادمة في دوري روشن",
        body=("متن طويل بما يكفي لاجتياز الحد الأدنى لطول الخبر المنشور. " * 6),
        status=ArticleStatus.PUBLISHED,
        category_id=category.id,
        author_id=users["editor"].id,
    )
    second.regenerate_slug()
    second.published_at = second.created_at
    db.session.add(second)
    db.session.commit()

    now_utc = datetime.now(timezone.utc).replace(microsecond=0)
    now_riyadh = now_utc.astimezone(service.RIYADH)
    # مباراة قادمة داخل الأسبوع الحالي (حتى لو نُفّذ الاختبار يوم أحد)
    week_end = service._week_end(now_riyadh)
    kick = week_end - timedelta(hours=1)
    if kick <= now_riyadh:
        kick = now_riyadh + timedelta(minutes=30)
    events = [
        _event(
            "1", _iso(now_utc - timedelta(days=3)), "post", "929", "8346",
            home_score=3, away_score=0,
            stadium="Kingdom Arena", city="King Fahd International Stadium",
        ),
        _event(
            "2", _iso(kick), "pre", "817", "2276",
            stadium="Prince Mohammed Bin Fahd Stadium", city="Dammam",
        ),
        # خارج نافذة الأسبوع: يجب ألّا يظهر
        _event(
            "3", _iso(now_utc + timedelta(days=20)), "pre", "929", "817",
            stadium="Kingdom Arena", city="Riyadh",
        ),
    ]
    monkeypatch.setattr(service, "fetch_scoreboards", lambda now: events)

    html = league.test_client().get("/").get_data(as_text=True)

    assert "دوري روشن السعودي" in html
    assert "مباريات هذا الأسبوع" in html
    assert "آخر النتائج" in html
    # الترتيب RTL: مباريات هذا الأسبوع يمين السلايدر، وآخر النتائج يساره،
    # ثم «أحدث الأخبار» بعرض كامل بعد الساحة (كما كانت قبل تغيير الأماكن)
    i_matches = html.index("مباريات هذا الأسبوع")
    i_hero = html.index("النصر يستعد لمباراة الجولة القادمة في دوري روشن")
    i_results = html.index("آخر النتائج")
    i_news = html.index("أحدث الأخبار")
    assert i_matches < i_hero < i_results < i_news
    assert "arena-center" in html
    # أسماء عربية وشعار محلي
    assert "الهلال" in html and "الأهلي" in html
    assert "النصر" in html and "الاتحاد" in html
    assert "img/teams/929.png" in html
    # النتيجة المنجزة
    assert '<span class="score">3<em>:</em>0</span>' in html
    # الملعب والمدينة بالعربية
    assert "أرضية المملكة أرينا" in html and "الرياض" in html
    assert "ملعب الأمير محمد بن فهد" in html and "الدمام" in html
    # التاريخ الهجري في شريحة مخصّصة
    assert 'class="match-hijri"' in html and "هـ" in html
    # المباراة البعيدة خارج نافذة الأسبوع
    far = (now_utc + timedelta(days=20)).astimezone(service.RIYADH)
    assert f"{far.day} {service.AR_MONTHS[far.month - 1]} {far.year}" not in html


def test_visible_fixture_window_ends_with_current_week():
    """«مباريات هذا الأسبوع» تنتهي بنهاية الأسبوع الحالي: مباراة الخميس من
    الأسبوع القادم لا تتسرّب إلى القائمة (لا نافذة +7 أيام مفتوحة)."""
    now = datetime(2026, 10, 8, 12, 0, tzinfo=service.RIYADH)  # الخميس 8 أكتوبر
    events = [
        _event("1", "2026-10-09T18:00Z", "pre", "929", "817",  # الجمعة — هذا الأسبوع
               stadium="Kingdom Arena", city="Riyadh"),
        _event("2", "2026-10-11T18:00Z", "pre", "929", "817",  # الأحد — هذا الأسبوع
               stadium="Kingdom Arena", city="Riyadh"),
        _event("3", "2026-10-15T18:00Z", "pre", "929", "817",  # الخميس القادم — خارج
               stadium="Kingdom Arena", city="Riyadh"),
    ]
    payload = service.build_payload(events, now)
    visible = service._visible(payload, now)

    assert [m["id"] for m in visible["fixtures"]] == ["1", "2"]
    assert service._week_end(now).isoformat() == "2026-10-12T00:00:00+03:00"


def test_build_payload_converts_time_venue_and_hijri_date():
    now = datetime.now(service.RIYADH)
    events = [
        _event(
            "10", "2026-10-09T18:00Z", "pre", "929", "817",
            stadium="Kingdom Arena", city="King Fahd International Stadium",
        )
    ]

    payload = service.build_payload(events, now)
    match = payload["fixtures"][0]

    assert match["status"] == "scheduled"
    assert match["time"] == "9:00 م"            # 18:00 UTC = 21:00 بتوقيت الرياض (بنظام 12 ساعة)
    assert match["date_greg"] == "9 أكتوبر 2026"
    assert match["date_hijri"] == "28 ربيع الآخر 1448"
    assert match["weekday"] == "الجمعة"
    assert match["stadium"] == "أرضية المملكة أرينا"
    assert match["city"] == "الرياض"           # اسم المدينة الإنجليزي هنا يعني الرياض
    assert match["home"]["name"] == "الهلال"
    assert match["away"]["name"] == "النصر"
    assert match["kickoff"].endswith("+03:00")


def test_league_reuses_fresh_cache_without_touching_the_network(league, monkeypatch):
    now_utc = datetime.now(timezone.utc).replace(microsecond=0)
    events = [
        _event(
            "1", _iso(now_utc + timedelta(days=1)), "pre", "817", "2276",
            stadium="Kingdom Arena", city="Riyadh",
        )
    ]
    monkeypatch.setattr(service, "fetch_scoreboards", lambda now: events)
    first = league.test_client().get("/")
    assert "النصر" in first.get_data(as_text=True)

    def _boom(now):
        raise AssertionError("لا يجوز نداء شبكة والكاش طازج")

    monkeypatch.setattr(service, "fetch_scoreboards", _boom)
    second = league.test_client().get("/")
    assert "النصر" in second.get_data(as_text=True)


def test_stale_cache_survives_a_failed_refresh(league, monkeypatch):
    now = datetime.now(service.RIYADH).replace(microsecond=0)
    stale = service.build_payload(
        [
            _event(
                "1",
                _iso(now + timedelta(days=1)),
                "pre",
                "817",
                "2276",
                stadium="Kingdom Arena",
                city="Riyadh",
            )
        ],
        now - timedelta(hours=2),  # كاش أقدم من المهلة ⇒ محاولة تحديث تفشل
    )
    service._write_cache(service._cache_path(), stale)

    def _boom(now):
        raise OSError("لا اتصال")

    monkeypatch.setattr(service, "fetch_scoreboards", _boom)
    html = league.test_client().get("/").get_data(as_text=True)
    assert "دوري روشن السعودي" in html
    assert "النصر" in html


def test_league_hides_quietly_when_the_source_fails_and_no_cache(league, monkeypatch):
    def _boom(now):
        raise OSError("لا اتصال")

    monkeypatch.setattr(service, "fetch_scoreboards", _boom)
    res = league.test_client().get("/")
    html = res.get_data(as_text=True)

    assert res.status_code == 200
    assert "دوري روشن" not in html
    assert "Traceback" not in html


def test_fetch_league_cli_refreshes_the_cache(league, monkeypatch):
    now_utc = datetime.now(timezone.utc).replace(microsecond=0)
    events = [
        _event(
            "1", _iso(now_utc + timedelta(days=1)), "pre", "929", "817",
            stadium="Kingdom Arena", city="Riyadh",
        ),
        _event(
            "2", _iso(now_utc - timedelta(days=2)), "post", "817", "8346",
            home_score=2, away_score=1,
            stadium="Kingdom Arena", city="Riyadh",
        ),
    ]
    monkeypatch.setattr(service, "fetch_scoreboards", lambda now: events)

    result = league.test_cli_runner().invoke(args=["fetch-league"])

    assert result.exit_code == 0, result.output
    assert "1 نتيجة" in result.output
    assert "1 مباراة قادمة" in result.output
    assert service._cache_path().exists()


def _summary_payload() -> dict:
    """ملخص ESPN مصغّر: هدف، ركلة جزاء، بطاقتان، تبديل، وصانع هدف."""
    return {
        "keyEvents": [
            {"type": {"type": "goal"}, "clock": {"displayValue": "4'"}, "team": {"id": "22022"},
             "participants": [{"athlete": {"displayName": "Tijjani Reijnders"}}]},
            {"type": {"type": "penalty---scored"}, "clock": {"displayValue": "67'"}, "team": {"id": "22022"},
             "participants": [{"athlete": {"displayName": "Mateo Retegui"}}]},
            {"type": {"type": "yellow-card"}, "clock": {"displayValue": "30'"}, "team": {"id": "22028"},
             "participants": [{"athlete": {"displayName": "John Buckley"}}]},
            {"type": {"type": "red-card"}, "clock": {"displayValue": "80'"}, "team": {"id": "22028"},
             "participants": [{"athlete": {"displayName": "Adi"}}]},
            {"type": {"type": "substitution"}, "clock": {"displayValue": "56'"}, "team": {"id": "22028"},
             "participants": [{"athlete": {"displayName": "Guga"}}, {"athlete": {"displayName": "Julien Domingues"}}]},
        ],
        "rosters": [
            {"team": {"id": "22022"}, "roster": [
                {"athlete": {"displayName": "Musab Al-Juwayr"}, "stats": [{"name": "goalAssists", "value": 1.0}]},
                {"athlete": {"displayName": "Tijjani Reijnders"}, "stats": [{"name": "goalAssists", "value": 0.0}]},
            ]},
        ],
    }


def test_summary_view_extracts_events_and_assists():
    view = service._summary_view(_summary_payload())

    assert [g["player"] for g in view["goals"]] == ["Tijjani Reijnders", "Mateo Retegui"]
    assert view["goals"][0]["team"] == "القادسية"
    assert view["goals"][1]["kind"] == "penalty"
    assert [c["kind"] for c in view["cards"]] == ["yellow", "red"]
    assert view["cards"][1]["team"] == "الخلود"
    assert view["subs"][0] == {
        "minute": "56'", "team": "الخلود", "in": "Guga", "out": "Julien Domingues",
    }
    assert view["assists"] == [{"player": "Musab Al-Juwayr", "team": "القادسية", "count": 1}]


def test_summary_view_returns_none_when_empty():
    assert service._summary_view({}) is None
    assert service._summary_view({"keyEvents": [], "rosters": []}) is None


def test_attach_summaries_links_events_to_finished_results_only(monkeypatch):
    payload = {"results": [{"id": "1"}, {"id": "2"}], "fixtures": [{"id": "3"}]}
    calls: list[str] = []

    def fake(event_id: str) -> dict:
        calls.append(event_id)
        return _summary_payload() if event_id == "1" else {}

    monkeypatch.setattr(service, "fetch_summary", fake)
    service._attach_summaries(payload)

    assert calls == ["1", "2"]  # المواعيد لا تُجلب لها ملخصات
    assert payload["results"][0]["summary"]["goals"][0]["team"] == "القادسية"
    assert "summary" not in payload["results"][1]
    assert "summary" not in payload["fixtures"][0]


def test_attach_summaries_survives_a_failed_match(monkeypatch):
    payload = {"results": [{"id": "1"}]}

    def boom(event_id: str) -> dict:
        raise OSError("لا اتصال")

    monkeypatch.setattr(service, "fetch_summary", boom)
    service._attach_summaries(payload)

    assert "summary" not in payload["results"][0]


def test_finished_match_renders_hover_summary(league, monkeypatch):
    now_utc = datetime.now(timezone.utc).replace(microsecond=0)
    events = [
        _event(
            "7", _iso(now_utc - timedelta(days=1)), "post", "817", "22028",
            home_score=2, away_score=0,
            stadium="Kingdom Arena", city="Riyadh",
        )
    ]
    monkeypatch.setattr(service, "fetch_scoreboards", lambda now: events)
    monkeypatch.setattr(service, "fetch_summary", lambda event_id: _summary_payload())

    html = league.test_client().get("/").get_data(as_text=True)

    assert "data-summary=" in html           # التلميح يحمل بيانات الحدث
    assert "summary-cue" in html             # إشارة «الملخص» للمباراة المنتهية
    assert "Tijjani Reijnders" in html       # اسم مسجّل الهدف داخل البيانات
    assert "goalAssists" not in html         # لا نكشف أسماء إحصاءات ESPN

