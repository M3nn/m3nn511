"""نظام سجلات غير حاجب (Asynchronous / Non-blocking) — Protocol 4.

المسار: LogRecord -> QueueHandler -> Queue -> QueueListener (خيط daemon) -> RotatingFileHandler

الكتابة على القرص تحدث في خيط منفصل، فلا ينتظر أي request path القرص.
عند امتلاء الطابور يُسقَط السجل بدل حجب الطلب. عند فشل التهيئة يرجع
التطبيق إلى معالج متزامن بدل أن ينهار.
"""
from __future__ import annotations

import atexit
import logging
import logging.handlers
import queue
import threading
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
DATE_FORMAT = "%(asctime)s"

_listener: logging.handlers.QueueListener | None = None
_lock = threading.Lock()
_dropped = 0


def _note_drop(record: logging.LogRecord) -> None:
    global _dropped
    _dropped += 1


def dropped_count() -> int:
    """عدد السجلات المُسقَطة بسبب امتلاء الطابور (لتشخيصه فقط)."""
    return _dropped


def _console_level(level_name: str) -> int:
    """نُخفي DEBUG من الطرفية حتى لا تضجّ، مع إبقائه في الملف."""
    return logging.INFO if level_name == "DEBUG" else logging.WARNING


def configure_logging(app) -> None:
    """يُستدعى مرّة واحدة من create_app. آمن للاستدعاء المتكرّر (idempotent)."""
    global _listener

    with _lock:
        if _listener is not None:
            return

        level = getattr(logging, app.config["LOG_LEVEL"], logging.INFO)
        log_dir = Path(app.config["LOG_DIR"])
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / app.config["LOG_FILE"]

        root = logging.getLogger("app")
        for old in list(root.handlers):
            root.removeHandler(old)
            old.close()
        root.setLevel(level)
        root.propagate = False

        file_handler = _file_handler(app, log_path, level)
        if not _start_listener(app, [file_handler, *_console_handler(app, level)], level):
            # تدهور آمن: كتابة متزامنة بدل انهيار التطبيق
            for h in (file_handler, *_console_handler(app, level)):
                root.addHandler(h)
            app.logger.warning("async logging unavailable, using synchronous handlers")
            return

        # يمنع تكرار السجلات عند waitress + Flask معاً
        logging.getLogger("waitress").setLevel(logging.WARNING)


def _file_handler(app, log_path: Path, level: int) -> logging.Handler:
    h = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=app.config["LOG_MAX_BYTES"],
        backupCount=app.config["LOG_BACKUP_COUNT"],
        encoding="utf-8",
    )
    h.setFormatter(logging.Formatter(LOG_FORMAT, "%Y-%m-%d %H:%M:%S"))
    h.setLevel(level)
    return h


def _console_handler(app, level: int) -> list[logging.Handler]:
    if not app.config["LOG_TO_STDERR"]:
        return []
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter(LOG_FORMAT, "%Y-%m-%d %H:%M:%S"))
    h.setLevel(_console_level(app.config["LOG_LEVEL"]))
    return [h]


def _start_listener(
    app, handlers: list[logging.Handler], level: int
) -> bool:
    """يشغّل خيط الاستماع. يُرجع False عند أي فشل (المتصل يتدهور بأمان)."""
    global _listener
    try:
        q: queue.Queue = queue.Queue(maxsize=1000)
        queue_handler = logging.handlers.QueueHandler(q)
        # عند امتلاء الطابور: incr العدّاد بدل رمي استثناء نحو المستخدم
        queue_handler.handleError = _note_drop  # type: ignore[method-assign]

        listener = logging.handlers.QueueListener(q, *handlers, respect_handler_level=True)
        listener.daemon = True
        listener.start()
        _listener = listener

        root = logging.getLogger("app")
        root.addHandler(queue_handler)
        app.logger.info("logging ready: async queue -> %s", _log_target(app))
        return True
    except Exception:  # pragma: no cover - مسار تدهور نادر جداً
        _listener = None
        return False


def _log_target(app) -> str:
    return str(Path(app.config["LOG_DIR"]) / app.config["LOG_FILE"])


def shutdown_logging() -> None:
    """يُغلق خيط الاستماع بأمان (يُستدعى عند exit)."""
    global _listener
    with _lock:
        if _listener is not None:
            _listener.stop()
            _listener = None


atexit.register(shutdown_logging)


def get_logger(name: str) -> logging.Logger:
    """يضمن أن كل سجلات التطبيق تحت جذر 'app' لتلتقطها الطابور."""
    if name == "app" or name.startswith("app."):
        return logging.getLogger(name)
    return logging.getLogger(f"app.{name}")
