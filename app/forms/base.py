"""مقوّم التحقق العربي — طبقة رقيقة فوق Flask-WTF/WTForms.

الغرض الوحيد: تحويل رسائل الأخطاء الإنجليزية التي يولّدها WTForms إلى عربي
قبل أن تصل إلى القوالب. لا يضيف أي حالة (state) ولا منطق عمل.

WTForms 3.x لا يضع اسم القيد داخل نص الرسالة، لذا نطابق على نص الرسالة
الإنجليزية نفسه ثم نحقن الأرقام المستخرجة منها.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from wtforms import Form, ValidationError

# (جزء مطابق من الرسالة الإنجليزية، النص العربي المقابل)
# الترتيب مهم: نختار أول تطابق.
_TRANSLATIONS: tuple[tuple[str, str], ...] = (
    ("This field is required", "هذا الحقل مطلوب."),
    ("Field must be between", "الطول المسموح بين {min} و {max} حرفاً."),
    ("Field must be at least", "الحد الأدنى {min} حرفاً."),
    ("Field cannot be longer than", "الحد الأقصى {max} حرفاً."),
    ("Field must be at most", "الحد الأقصى {max} حرفاً."),
    ("Not a valid", "القيمة المدخلة غير صحيحة."),
    ("Invalid", "القيمة المدخلة غير صحيحة."),
    ("must be equal to", "القيمتان غير متطابقتين."),
)

_NUMBERS = re.compile(r"\d+")


def _translate(message: str) -> str:
    """يترجم رسالة WTForms إلى عربية، ويملأ {min}/{max} بأرقام الرسالة."""
    numbers = [int(n) for n in _NUMBERS.findall(message)]
    for needle, arabic in _TRANSLATIONS:
        if needle not in message:
            continue
        values: dict[str, int | str] = {}
        if "{min}" in arabic:
            values["min"] = numbers[0] if numbers else ""
        if "{max}" in arabic:
            values["max"] = numbers[1] if len(numbers) > 1 else values.get("min", "")
        return arabic.format(**values)
    # رسائلنا العربية المخصّصة (at_most_chars و validate_image_url) تمرّ كما هي
    return message


def _localize(form: Form) -> None:
    """يستبدل field.errors بنسخ عربية، مرّة واحدة عند إنشاء النموذج."""
    for name, field in form._fields.items():
        if field.errors:
            label = field.label.text or name
            field.errors = [f"{label} — {_translate(m)}" for m in field.errors]
            form.form_errors.append(f"{label} — الرجاء تصحيح الحقل.")
        # أسماء الحقول تبقى إنجليزية في الـ HTML بينما التسميات عربية
        field.label.text = field.label.text or name


class ArabicForm(Form):
    """نموذج أساسي: رسائل عربية + class="form-control" على كل الحقول."""

    class Meta:
        def bind_field(self, form, unbound_field, options):  # noqa: D102
            render_kw = options.setdefault("render_kw", {})
            css = render_kw.setdefault("class", "form-control")
            if "form-control" not in css and "form-check-input" not in css:
                render_kw["class"] = f"{css} form-control".strip()
            return unbound_field.bind(form=form, **options)

    def validate(self, extra_validators=None):
        """يترجم أخطاء التحقق بعد أن تشتغل المُدقِّقات.

        لا يمكن الترجمة في __init__ لأن WTForms يملأ field.errors أثناء
        validate() فقط، أي بعد إنشاء النموذج. validate_on_submit() يمرّ من هنا.
        """
        ok = super().validate(extra_validators=extra_validators)
        _localize(self)
        return ok


def validate_image_url(form, field) -> None:
    """يتحقق أن القيمة رابط http/https صالح — يُستعمل على cover_image_url فقط.

    توقيع (form, field) هو العرف المتّبع في WTForms 3.x لـ validation المضمّن.
    """
    parsed = urlparse((field.data or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValidationError("أدخل رابط صورة صالحاً يبدأ بـ http أو https.")


def at_most_chars(limit: int, message: str):
    """قيد طول بسيط برسالة عربية (بديل Message eq لـ WTForms بدون تعقيد)."""

    def _check(form, field):
        if field.data and len(field.data) > limit:
            raise ValidationError(message)

    return _check