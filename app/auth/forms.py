"""نماذج المصادقة — تسجيل الدخول للموظفين فقط (لا يوجد تسجيل عام)."""
from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField
from wtforms.validators import DataRequired, Length

from app.forms.base import ArabicForm


class LoginForm(ArabicForm, FlaskForm):
    username = StringField(
        "اسم المستخدم",
        validators=[DataRequired(), Length(min=3, max=80)],
        render_kw={"autofocus": True, "autocomplete": "username"},
    )
    password = PasswordField(
        "كلمة المرور",
        validators=[DataRequired(), Length(min=6, max=128)],
        render_kw={"autocomplete": "current-password"},
    )
