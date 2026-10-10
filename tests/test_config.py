"""اختيار الإعدادات: الإنتاج بلا DEBUG، وإخفاء الحسابات التجريبية عن الزوار."""
from __future__ import annotations

from app.config import DevConfig, ProdConfig, TestConfig, resolve_config


def test_prod_config_disables_debug():
    config = ProdConfig()
    assert config.DEBUG is False
    assert config.TESTING is False


def test_resolve_config_by_name():
    assert isinstance(resolve_config("dev"), DevConfig)
    assert isinstance(resolve_config("prod"), ProdConfig)
    assert isinstance(resolve_config("test"), TestConfig)


def test_resolve_config_default_follows_environment(monkeypatch):
    monkeypatch.delenv("TESTING", raising=False)

    monkeypatch.setenv("APP_ENV", "production")
    assert isinstance(resolve_config(None), ProdConfig)

    monkeypatch.setenv("APP_ENV", "development")
    assert isinstance(resolve_config(None), DevConfig)


def test_login_page_hides_demo_accounts_when_not_debug(client):
    body = client.get("/auth/login").get_data(as_text=True)
    assert "حسابات تجريبية" not in body