"""نموذج التصنيف — تحكّم إداري كامل."""
from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import IntegerField, StringField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.forms.base import ArabicForm


class CategoryForm(ArabicForm, FlaskForm):
    name = StringField(
        "اسم التصنيف",
        validators=[DataRequired(), Length(min=2, max=80)],
        render_kw={"placeholder": "مثال: كرة القدم"},
    )
    sort_order = IntegerField(
        "ترتيب الظهور",
        validators=[Optional(), NumberRange(min=0, max=9999)],
        default=0,
        render_kw={"dir": "ltr", "placeholder": "0"},
    )
    submit = StringField("حفظ")