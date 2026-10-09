"""نموذج المهمة التحريرية."""
from __future__ import annotations

import datetime as dt

from flask_wtf import FlaskForm
from wtforms import DateField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from app.forms.base import ArabicForm, at_most_chars
from app.models import PRIORITY_LABELS, TASK_STATUS_LABELS, Priority, TaskStatus

DESCRIPTION_MAX = 4000


class TaskForm(ArabicForm, FlaskForm):
    title = StringField(
        "عنوان المهمة",
        validators=[DataRequired(), Length(min=5, max=250)],
        render_kw={"placeholder": "مثال: إعداد تقرير عن مباراة الأمس"},
    )
    description = TextAreaField(
        "الوصف",
        validators=[
            Optional(),
            at_most_chars(DESCRIPTION_MAX, "الوصف طويل جداً (4000 حرف كحد أقصى)."),
        ],
        render_kw={"rows": 6, "placeholder": "تفاصيل إضافية ومصادر ومعايير إنجاز."},
    )
    status = SelectField(
        "الحالة",
        choices=[(s.value, TASK_STATUS_LABELS[s]) for s in TaskStatus],
        default=TaskStatus.TODO.value,
    )
    priority = SelectField(
        "الأولوية",
        choices=[(p.value, PRIORITY_LABELS[p]) for p in Priority],
        default=Priority.MED.value,
    )
    assignee_id = SelectField("المكلف", coerce=int, validators=[Optional()])
    article_id = SelectField("الخبر المرتبط", coerce=int, validators=[Optional()])
    due_date = DateField("تاريخ الاستحقاق", validators=[Optional()], render_kw={"dir": "ltr"})
    submit = StringField("حفظ")

    def validate_due_date(self, field: DateField) -> None:
        """WTForms 3.x يمرّر خطأ القيمة عبر الاستثناء نفسه، لا عبر القيمة المرفوعة."""
        if field.data and field.data < dt.date.today():
            raise ValidationError("تاريخ الاستحقاق لا يكون في الماضي.")
