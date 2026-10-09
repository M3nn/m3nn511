"""اختبارات طبقة الذكاء الاصطناعي — بلا أي نداء شبكة.

كل اختبار يستبدل عميل OpenAI بنتيجة وهمية، فيتحقق من سلوك الواجهة،
والتسجيل في ai_usage، ورسائل الخطأ العربية.
"""

from __future__ import annotations

import json
import types

import pytest

from app.ai import service as ai
from app.extensions import db
from app.models import AIUsage, ArticleStatus
from tests.conftest import login

BRIEF = "نحتاج تغطية ما قبل مباراة الغد بين الفريقين في الدوري المحلي."


class _FakeUsage:
    def __init__(self, i: int, o: int):
        self.input_tokens = i
        self.output_tokens = o


def _fake_response(text: str, i: int = 120, o: int = 40):
    return types.SimpleNamespace(output_text=text, usage=_FakeUsage(i, o))


@pytest.fixture()
def fake_openai(monkeypatch):
    """كائن لتعيين رد النموذج، ويمنع أي اتصال حقيقي بالشبكة."""

    class Box:
        text = ""
        calls: list = []
        raise_with = None

    def _create(**kwargs):
        box.calls.append(kwargs)
        if box.raise_with is not None:
            raise box.raise_with
        return _fake_response(box.text)

    box = Box()
    monkeypatch.setattr(
        ai,
        "_client",
        lambda: types.SimpleNamespace(responses=types.SimpleNamespace(create=_create)),
    )
    return box


# ---------------- AI-1: التلخيص ----------------


def test_summarize_returns_text_and_records_usage(app, fake_openai, article):
    fake_openai.text = "  موجز الخبر في جملة واحدة مختصرة.  "
    result = ai.summarize(article.body)

    assert result.data == "موجز الخبر في جملة واحدة مختصرة."
    assert result.input_tokens == 120
    assert result.output_tokens == 40
    assert result.lat_ms >= 0

    usage = db.session.scalar(db.select(AIUsage).where(AIUsage.feature == "summarize"))
    assert usage is not None
    assert usage.ok is True
    assert usage.total_tokens == 160
    assert usage.model == app.config["AI_MODEL"]


def test_summarize_uses_configured_model(app, fake_openai, article):
    fake_openai.text = "ملخص."
    ai.summarize(article.body)
    assert fake_openai.calls[0]["model"] == app.config["AI_MODEL"]
    assert "instructions" in fake_openai.calls[0]


def test_summarize_rejects_short_body(app, fake_openai, article):
    with pytest.raises(ai.AIFailure) as exc:
        ai.summarize("قصير جدا")
    assert exc.value.status == 400


def test_summarize_trims_input_to_config_limit(app, fake_openai, article):
    fake_openai.text = "ملخص."
    article.body = "ط" * (app.config["AI_MAX_INPUT_CHARS"] * 3)
    db.session.commit()
    ai.summarize(article.body)
    assert len(fake_openai.calls[0]["input"]) <= app.config["AI_MAX_INPUT_CHARS"]


def test_empty_model_output_raises_and_records_failure(app, fake_openai, article):
    fake_openai.text = "   "
    with pytest.raises(ai.AIFailure) as exc:
        ai.summarize(article.body)
    assert exc.value.status == 502

    usage = db.session.scalar(db.select(AIUsage).where(AIUsage.feature == "summarize"))
    assert usage is not None and usage.ok is False


def test_api_error_maps_to_arabic_502(app, fake_openai, article):
    from openai import APIError

    fake_openai.raise_with = APIError("boom", None, body=None)
    with pytest.raises(ai.AIFailure) as exc:
        ai.summarize(article.body)
    assert exc.value.status == 502
    assert "تعذّر" in exc.value.message


def test_timeout_maps_to_504(app, fake_openai, article):
    from openai import APITimeoutError

    fake_openai.raise_with = APITimeoutError(request=None)
    with pytest.raises(ai.AIFailure) as exc:
        ai.summarize(article.body)
    assert exc.value.status == 504


def test_rate_limit_maps_to_429(app, fake_openai, article):
    from openai import RateLimitError

    fake_openai.raise_with = RateLimitError(
        "slow down",
        response=types.SimpleNamespace(status_code=429, headers={}, request=None),
        body=None,
    )
    with pytest.raises(ai.AIFailure) as exc:
        ai.summarize(article.body)
    assert exc.value.status == 429


def test_unexpected_error_maps_to_500(app, fake_openai, article):
    fake_openai.raise_with = ValueError("unexpected")
    with pytest.raises(ai.AIFailure) as exc:
        ai.summarize(article.body)
    assert exc.value.status == 500


def test_no_api_key_raises_clear_503(app, article):
    app.config["OPENAI_API_KEY"] = ""
    with pytest.raises(ai.AIFailure) as exc:
        ai.summarize(article.body)
    assert exc.value.status == 503
    assert "OPENAI_API_KEY" in exc.value.message


# ---------------- AI-2: اقتراح المهام ----------------


def test_suggest_tasks_parses_clean_json(app, fake_openai):
    fake_openai.text = json.dumps([
        {"title": "كتابة تقرير المباراة", "priority": "high"},
        {"title": "مراجعة العناوين", "priority": "low"},
    ])
    result = ai.suggest_tasks(BRIEF)
    assert len(result.data) == 2
    assert result.data[0]["title"] == "كتابة تقرير المباراة"
    assert result.data[0]["priority"] == "high"


def test_suggest_tasks_tolerates_wrapped_json(app, fake_openai):
    fake_openai.text = "إليك الاقتراحات:\n" + json.dumps([{"title": "مهمة واحدة مقترحة"}])
    result = ai.suggest_tasks(BRIEF)
    assert result.data == [{"title": "مهمة واحدة مقترحة", "priority": "med"}]


def test_suggest_tasks_drops_invalid_entries(app, fake_openai):
    fake_openai.text = json.dumps([
        {"title": "   ", "priority": "high"},
        {"priority": "low"},
        "نص نصي",
        {"title": "مهمة صالحة", "priority": "bogus"},
    ])
    result = ai.suggest_tasks(BRIEF)
    assert result.data == [{"title": "مهمة صالحة", "priority": "med"}]


def test_suggest_tasks_respects_limit(app, fake_openai):
    fake_openai.text = json.dumps([{"title": f"مهمة رقم {i}"} for i in range(1, 20)])
    result = ai.suggest_tasks(BRIEF)
    assert len(result.data) == app.config["AI_MAX_SUGGESTIONS"]


def test_suggest_tasks_rejects_garbage_output(app, fake_openai):
    fake_openai.text = "لا يوجد أي JSON هنا."
    with pytest.raises(ai.AIFailure) as exc:
        ai.suggest_tasks(BRIEF)
    assert exc.value.status == 502


def test_suggest_tasks_rejects_short_brief(app, fake_openai):
    with pytest.raises(ai.AIFailure) as exc:
        ai.suggest_tasks("قصير")
    assert exc.value.status == 400


# ---------------- المسارات ----------------


def test_ai_summary_route_fills_article(client, users, article, fake_openai):
    fake_openai.text = "ملخص مولد للاختبار."
    login(client, "editor", "editor123")

    r = client.post(f"/editor/articles/{article.id}/ai-summary",
                    headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert "ملخص مولد للاختبار" in r.get_data(as_text=True)

    db.session.refresh(article)
    assert article.summary == "ملخص مولد للاختبار."


def test_ai_summary_route_returns_arabic_error_without_key(client, users, article):
    login(client, "editor", "editor123")
    client.application.config["OPENAI_API_KEY"] = ""

    r = client.post(f"/editor/articles/{article.id}/ai-summary",
                    headers={"HX-Request": "true"})
    assert r.status_code == 503
    assert "OPENAI_API_KEY" in r.get_data(as_text=True)

    # التطبيق يبقى يعمل بعد الفشل
    assert client.get("/").status_code == 200


def test_ai_summary_route_forbidden_for_writer(client, users, article, fake_openai):
    login(client, "writer", "writer123")
    r = client.post(f"/editor/articles/{article.id}/ai-summary")
    assert r.status_code == 403


def test_suggest_route_returns_partial(client, users, fake_openai):
    fake_openai.text = json.dumps([{"title": "مهمة مقترحة عبر المسار", "priority": "med"}])
    login(client, "writer", "writer123")

    r = client.post("/tasks/suggest", data={"brief": BRIEF},
                    headers={"HX-Request": "true"})
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "مهمة مقترحة عبر المسار" in body
    assert "<html" not in body


def test_suggest_page_renders_for_editor(client, users, app):
    login(client, "editor", "editor123")
    assert client.get("/tasks/suggest").status_code == 200


def test_suggest_requires_login(client, app):
    r = client.post("/tasks/suggest", data={"brief": "أي نص هنا للاختبار"})
    assert r.status_code == 302


def test_ai_usage_rows_are_scoped_per_feature(app, fake_openai, article):
    fake_openai.text = "ملخص."
    ai.summarize(article.body)
    fake_openai.text = json.dumps([{"title": "مهمة"}])
    ai.suggest_tasks(BRIEF)

    features = {u.feature for u in db.session.scalars(db.select(AIUsage)).all()}
    assert features == {"summarize", "task_suggestions"}


def test_ai_failure_does_not_break_article_flow(client, users, article, fake_openai):
    """سجل الاستهلاك الفاشل لا يمنع بقاء المقال نشطا في لوحة التحرير."""
    from openai import APIError

    fake_openai.raise_with = APIError("boom", None, body=None)
    login(client, "editor", "editor123")
    client.post(f"/editor/articles/{article.id}/ai-summary",
                headers={"HX-Request": "true"})

    db.session.refresh(article)
    assert article.status is ArticleStatus.PUBLISHED
    assert client.get("/editor").status_code == 200


def test_is_configured_reflects_key(app):
    from app.ai.service import is_configured

    app.config["OPENAI_API_KEY"] = "sk-test"
    assert is_configured() is True
    app.config["OPENAI_API_KEY"] = ""
    assert is_configured() is False