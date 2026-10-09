"""طبقة الذكاء الاصطناعي — نقطتا دخول فقط (تلخيص + اقتراح مهام).

كل نداء: يمرّ عبر try/except موحّد، يُسجَّل في ai_usage، ويعيد نتيجة نظيفة
أو يرمي AIFailure برسالة عربية جاهزة للعرض. لا يوجد streaming ولا agents.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from openai import APIError, APITimeoutError, OpenAI, RateLimitError

from app.extensions import db
from app.models import AIUsage

log = logging.getLogger("app.ai")

# حدود صارمة على مُدخلات المستخدم: تقلّل التكلفة وتمنع تجاوز context
MAX_BRIEF_CHARS = 4000
_SUMMARY_INSTRUCTIONS = (
    "أنت محرّر رياضي سعودي. لخّص النص التالي بالعربية الفصحى في جملتين إلى ثلاث "
    "جمل فقط. لا تضف معلومات غير موجودة في النص. لا تستعمل عناوين ولا قوائم. "
    "أعد الجمل مباشرة دون أي مقدمات."
)
_TASKS_INSTRUCTIONS = (
    "أنت مشرف تحريري في موقع أخبار رياضية سعودي. اقترح مهام تحريرية عملية "
    "من النص المعطى. أعد مصفوفة JSON فقط بلا أي نص إضافي، كل عنصر: "
    '{"title": "عنوان المهمة بالعربية", "priority": "low|med|high"}. '
    "من 3 إلى 5 مهام، عناوين قصيرة لا تتجاوز 80 حرفاً."
)
_JSON_BLOCK = re.compile(r"\[.*\]", re.DOTALL)


class AIFailure(Exception):
    """خطأ AI موحّد برسالة عربية — لا يسرّب تفاصيل المزوّد للمستخدم."""

    def __init__(self, message: str, status: int = 503) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class AIResult:
    data: Any
    model: str
    input_tokens: int
    output_tokens: int
    lat_ms: int


def is_configured() -> bool:
    from flask import current_app

    return bool(current_app.config.get("OPENAI_API_KEY"))


def _client() -> OpenAI:
    from flask import current_app

    key = current_app.config.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise AIFailure("خدمة الذكاء الاصطناعي غير مهيّأة. أضف OPENAI_API_KEY في ملف .env ثم أعد تشغيل الخادم.")
    return OpenAI(api_key=key, timeout=current_app.config["AI_TIMEOUT"], max_retries=1)


def _call(feature: str, instructions: str, payload: str, max_tokens: int) -> AIResult:
    """النداء الموحّد: بناء الطلب، القياس، التسجيل، وتحويل الأخطاء.

    الاستدعاء متزامن بقرار تصميمي: الطلب واحد ومحدود المخرجات، فلا داعي
    لعقدة خلفية (Celery/thread) تُضيف فشلاً جديداً مقابل توفير ثوانٍ.
    """
    from flask import current_app

    cfg = current_app
    model = cfg.config["AI_MODEL"]
    started = time.perf_counter()
    tokens_in = tokens_out = 0
    ok = True

    log.info("ai.start feature=%s model=%s chars=%d", feature, model, len(payload))
    try:
        response = _client().responses.create(
            model=model,
            instructions=instructions,
            input=payload,
            max_output_tokens=max_tokens,
        )
        text = (getattr(response, "output_text", "") or "").strip()
        usage = getattr(response, "usage", None)
        tokens_in = int(getattr(usage, "input_tokens", 0) or 0)
        tokens_out = int(getattr(usage, "output_tokens", 0) or 0)
        if not text:
            raise AIFailure("لم يُرجع النموذج أي نص. حاول مرة أخرى.", status=502)
    except AIFailure as exc:
        ok = False
        _record(feature, model, 0, 0, started, ok=False, user_id=_current_user_id())
        log.error("ai.empty feature=%s model=%s", feature, model)
        raise exc
    except RateLimitError:
        ok = False
        _record(feature, model, 0, 0, started, ok=False, user_id=_current_user_id())
        log.warning("ai.rate_limited feature=%s model=%s", feature, model)
        raise AIFailure("تم تجاوز حد الاستخدام المؤقت للخدمة. حاول بعد قليل.", status=429) from None
    except APITimeoutError:
        ok = False
        _record(feature, model, 0, 0, started, ok=False, user_id=_current_user_id())
        log.warning("ai.timeout feature=%s model=%s seconds=%s", feature, model, cfg.config["AI_TIMEOUT"])
        raise AIFailure("استغرق الطلب وقتاً طويلاً. جرّب نصاً أقصر أو أعد المحاولة.", status=504) from None
    except APIError as exc:
        ok = False
        _record(feature, model, 0, 0, started, ok=False, user_id=_current_user_id())
        log.error("ai.api_error feature=%s model=%s error=%s", feature, model, exc.__class__.__name__)
        raise AIFailure("تعذّر الاتصال بخدمة الذكاء الاصطناعي. تحقق من المفتاح والاتصال.", status=502) from None
    except Exception as exc:  # شبكة/JSON/غير متوقع
        ok = False
        _record(feature, model, 0, 0, started, ok=False, user_id=_current_user_id())
        log.exception("ai.unexpected feature=%s model=%s error=%s", feature, model, exc)
        raise AIFailure("حدث خطأ غير متوقع أثناء طلب التلخيص.", status=500) from None

    lat_ms = int((time.perf_counter() - started) * 1000)
    _record(feature, model, tokens_in, tokens_out, started, ok=True, user_id=_current_user_id())
    log.info(
        "ai.ok feature=%s model=%s in=%d out=%d lat_ms=%d",
        feature, model, tokens_in, tokens_out, lat_ms,
    )
    return AIResult(data=text, model=model, input_tokens=tokens_in, output_tokens=tokens_out, lat_ms=lat_ms)


def _current_user_id() -> int | None:
    from flask_login import current_user

    return current_user.id if getattr(current_user, "is_authenticated", False) else None


def _record(feature: str, model: str, tok_in: int, tok_out: int, started: float,
            *, ok: bool, user_id: int | None) -> None:
    """كتابة سجل الاستهلاك. الفشل هنا لا يجوز أن يُفشل الطلب الأصلي."""
    try:
        db.session.add(
            AIUsage(
                user_id=user_id, feature=feature, model=model,
                input_tokens=tok_in, output_tokens=tok_out,
                lat_ms=int((time.perf_counter() - started) * 1000), ok=ok,
            )
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        log.exception("ai.usage_record_failed feature=%s", feature)


# ---------------- الميزة AI-1: تلخيص خبر ----------------

def summarize(body: str) -> AIResult:
    """يختصر متن خبر إلى 2–3 جمل عربية."""
    from flask import current_app

    text = (body or "").strip()
    if len(text) < 80:
        raise AIFailure("المتن قصير جداً للتلخيص (80 حرفاً على الأقل).", status=400)
    limit = current_app.config["AI_MAX_INPUT_CHARS"]
    result = _call("summarize", _SUMMARY_INSTRUCTIONS, text[:limit],
                   current_app.config["AI_MAX_OUTPUT_TOKENS"])
    return AIResult(
        data=" ".join(result.data.split()),
        model=result.model, input_tokens=result.input_tokens,
        output_tokens=result.output_tokens, lat_ms=result.lat_ms,
    )


# ---------------- الميزة AI-2: اقتراح مهام تحريرية ----------------

def suggest_tasks(brief: str) -> AIResult:
    """يحوّل نصاً حرّاً إلى قائمة مهام تحريرية منظّمة."""
    from flask import current_app

    text = (brief or "").strip()
    if len(text) < 20:
        raise AIFailure("اكتب وصفاً أوضح (20 حرفاً على الأقل) للحصول على اقتراحات.", status=400)
    result = _call("task_suggestions", _TASKS_INSTRUCTIONS, text[:MAX_BRIEF_CHARS], 700)
    tasks = _parse_tasks(result.data, current_app.config["AI_MAX_SUGGESTIONS"])
    if not tasks:
        raise AIFailure("لم يُرجع النموذج اقتراحات صالحة. أعد صياغة الطلب.", status=502)
    return AIResult(
        data=tasks, model=result.model, input_tokens=result.input_tokens,
        output_tokens=result.output_tokens, lat_ms=result.lat_ms,
    )


def _parse_tasks(raw: str, limit: int) -> list[dict]:
    """يتحمّل JSON نظيفاً أو ملفوفاً بنص. يعيد فقط ما هو صالح للعرض."""
    payload: Any = None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        match = _JSON_BLOCK.search(raw)
        if not match:
            return []
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
    if not isinstance(payload, list):
        return []

    allowed = {"low", "med", "high"}
    out: list[dict] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()[:120]
        if not title:
            continue
        priority = str(item.get("priority", "med")).strip().lower()
        out.append({"title": title, "priority": priority if priority in allowed else "med"})
        if len(out) >= limit:
            break
    return out
