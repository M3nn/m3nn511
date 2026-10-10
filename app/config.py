"""إعدادات التطبيق. تُقرأ من متغيّرات البيئة عبر .env (أو .env.local للتجاوز)."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent

# .env أولاً، ثم .env.local فوقه (يتجاوز القيم أثناء التطوير)
load_dotenv(ROOT_DIR / ".env")
load_dotenv(ROOT_DIR / ".env.local", override=True)


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _db_uri() -> str:
    """رابط قاعدة البيانات من DATABASE_URL، مع تحويل روابط Postgres العادية
    (postgres:// أو postgresql://) تلقائياً إلى مشغّل psycopg الإصدار الثالث
    المثبّت في المتطلبات — فلا يحتاج المستخدم لمعرفة صيغة SQLAlchemy."""
    uri = os.getenv(
        "DATABASE_URL", f"sqlite:///{(ROOT_DIR / 'instance' / 'app.db').as_posix()}"
    )
    for old, new in (("postgres://", "postgresql+psycopg://"),
                     ("postgresql://", "postgresql+psycopg://")):
        if uri.startswith(old):
            return new + uri[len(old):]
    return uri


def _engine_options(uri: str) -> dict:
    """خيارات المحرك حسب نوع القاعدة: SQLite لها قيد المفاتيح الأجنبية وقفل
    الخيوط، وقواعد الشبكة (Postgres…) لها تجميع اتصالات صحيح للخوادم."""
    if not uri.startswith("sqlite"):
        return {
            "pool_pre_ping": True,
            "pool_size": int(os.getenv("DB_POOL_SIZE", "5")),
            "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "10")),
        }
    # مطلوب لتفعيل قيد المفاتيح الأجنبية في SQLite
    return {
        "connect_args": {"check_same_thread": False, "timeout": 15},
        "pool_pre_ping": True,
    }


class Config:
    """القيم المشتركة بين بيئات التشغيل."""

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-insecure-key-change-me")
    SQLALCHEMY_DATABASE_URI = _db_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = _engine_options(SQLALCHEMY_DATABASE_URI)

    # ---- مسؤول أول يُنشأ تلقائياً عند الإقلاع إن كانت القاعدة فارغة ----
    # مفيد للنشر على استضافات ذات ملفات مؤقتة (مثل Render المجاني) حيث تعاد
    # تهيئة القاعدة بعد كل إعادة تشغيل. تجاهل كليهما لإبقاء القاعدة بلا مستخدمين.
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "").strip()
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()
    ADMIN_DISPLAY_NAME = os.getenv("ADMIN_DISPLAY_NAME", "").strip()

    # حجم الصفحة الموحّد عبر الموقع كله
    ITEMS_PER_PAGE = int(os.getenv("ITEMS_PER_PAGE", "13"))
    ITEMS_PER_PAGE_ADMIN = 20

    # ---- الذكاء الاصطناعي ----
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
    AI_MODEL = os.getenv("AI_MODEL", "gpt-6-luna").strip()
    AI_TIMEOUT = float(os.getenv("AI_TIMEOUT", "45"))
    AI_MAX_INPUT_CHARS = int(os.getenv("AI_MAX_INPUT_CHARS", "6000"))
    AI_MAX_OUTPUT_TOKENS = int(os.getenv("AI_MAX_OUTPUT_TOKENS", "300"))
    AI_MAX_SUGGESTIONS = int(os.getenv("AI_MAX_SUGGESTIONS", "5"))

    # ---- دوري روشن السعودي ----
    # LEAGUE_ENABLED=0 يطفئ القسم كلياً (الاختبارات تبدأ مطفأة دائماً)
    LEAGUE_ENABLED = _flag("LEAGUE_ENABLED", True)
    LEAGUE_TTL = int(os.getenv("LEAGUE_TTL", "600"))          # ثوانٍ بين التحديثين
    LEAGUE_TIMEOUT = float(os.getenv("LEAGUE_TIMEOUT", "5"))  # مهلة نداء ESPN
    LEAGUE_CACHE_DIR = os.getenv("LEAGUE_CACHE_DIR", "").strip()  # فارغ ⇒ instance/

    # ---- السجلات ----
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_DIR = os.getenv("LOG_DIR", str(ROOT_DIR / "logs"))
    LOG_FILE = os.getenv("LOG_FILE", "app.log")
    LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", str(2 * 1024 * 1024)))
    LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))
    LOG_TO_STDERR = _flag("LOG_TO_STDERR", True)

    @staticmethod
    def init_app(app) -> None:
        """إنشاء مجلدات المخرجات قبل أي كتابة."""
        Path(app.config["LOG_DIR"]).mkdir(parents=True, exist_ok=True)
        db_path = app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
        if db_path and db_path != app.config["SQLALCHEMY_DATABASE_URI"]:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)


class DevConfig(Config):
    DEBUG = True
    TEMPLATES_AUTO_RELOAD = True


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    LOG_TO_STDERR = False
    OPENAI_API_KEY = "test-key-not-used"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    # قسم الدوري يبدأ مطفأً: أي اختبار يحتاجه يشعله ويستبدل fetch_scoreboards
    LEAGUE_ENABLED = False
    # كاش معزول عن instance/ الحقيقية حتى لو شُغِل القسم في اختبار
    LEAGUE_CACHE_DIR = str(Path(tempfile.gettempdir()) / "nassa_league_test")


def resolve_config(name: str | None):
    """يحوّل اسم الإعداد إلى كلاس فعلي، مع كاشف صغير لتفادي الاستيراد الدائري."""
    table = {"dev": DevConfig, "test": TestConfig, "default": DevConfig}
    if name:
        try:
            return table[name]()
        except KeyError:
            raise ValueError(
                f"Unknown config '{name}'. Choose one of: {', '.join(sorted(table))}"
            ) from None
    return (TestConfig if os.getenv("TESTING") else DevConfig)()
