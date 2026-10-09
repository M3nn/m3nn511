"""نموذج المقال — إنشاء/تعديل من لوحة التحرير."""
from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional

from app.forms.base import ArabicForm, at_most_chars, validate_image_url
from app.models import ARTICLE_STATUS_LABELS, ArticleStatus

# أقصى طول للمتن: يمنع إغراق AI بالطلبات ويبقي الصفحة قابلة للقراءة
BODY_MAX = 60_000


class ArticleForm(ArabicForm, FlaskForm):
    title = StringField(
        "العنوان",
        validators=[DataRequired(), Length(min=10, max=250)],
        render_kw={"placeholder": "مثال: النصر يفتتح الدوري بفوز عريض"},
    )
    body = TextAreaField(
        "المتن",
        validators=[DataRequired(), Length(min=80, max=BODY_MAX)],
        render_kw={"rows": 18, "placeholder": "اكتب المتن كاملاً. افصل بين الفقرات بسطر فارغ."},
    )
    summary = TextAreaField(
        "الملخص",
        validators=[Optional(), at_most_chars(600, "الملخص طويل جداً (600 حرف كحد أقصى).")],
        render_kw={"rows": 3, "placeholder": "اتركه فارغاً ثم اضغط «تلخيص بالذكاء الاصطناعي»."},
    )
    category_id = SelectField("التصنيف", coerce=int, validators=[Optional()])
    cover_image_url = StringField(
        "رابط صورة الغلاف",
        validators=[Optional(), at_most_chars(500, "الرابط طويل جداً."), validate_image_url],
        render_kw={"placeholder": "https://…", "dir": "ltr"},
    )
    status = SelectField(
        "الحالة",
        choices=[(s.value, ARTICLE_STATUS_LABELS[s]) for s in ArticleStatus],
        default=ArticleStatus.DRAFT.value,
    )
    submit = StringField("حفظ")
