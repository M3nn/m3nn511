"""اختبارات نظام السجلات — الهدف: الكتابة لا تحجب أي request path."""

from __future__ import annotations

import logging
import logging.handlers
import threading
import time
from pathlib import Path

from app.core import logging_setup


def _wait_for(path: Path, needle: str, timeout: float = 2.0) -> bool:
    """السجل يُكتب في خيط منفصل، فننتظر ظهوره بدل تحقق فوري."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists() and needle in path.read_text(encoding="utf-8"):
            return True
        time.sleep(0.02)
    return False


def test_log_file_is_created_and_receives_records(app):
    log_path = Path(app.config["LOG_DIR"]) / app.config["LOG_FILE"]
    logging.getLogger("app.test").warning("رسالة اختبار السجلات")
    assert _wait_for(log_path, "رسالة اختبار السجلات")


def test_queue_handler_is_attached_not_direct_file_handler(app):
    root = logging.getLogger("app")
    queue_handlers = [h for h in root.handlers if isinstance(h, logging.handlers.QueueHandler)]
    direct_file = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert queue_handlers, "يجب أن يمر كل سجل عبر QueueHandler"
    assert not direct_file, "لا يُكتب للملف مباشرة من مسار الطلب"


def test_listener_thread_is_daemon(app):
    assert logging_setup._listener is not None
    assert logging_setup._listener.daemon is True


def test_record_is_written_from_listener_thread(app):
    """نثبت أن الإرسال للمعالج يحدث في خيط الاستماع لا خيط الطلب."""
    log_path = Path(app.config["LOG_DIR"]) / app.config["LOG_FILE"]
    handler = logging_setup._listener.handlers[0]
    seen: set[int] = set()
    original = handler.emit

    def spy(record):
        seen.add(threading.get_ident())
        return original(record)

    handler.emit = spy
    try:
        logging.getLogger("app.test").info("تحقق من الخيط")
        assert _wait_for(log_path, "تحقق من الخيط")
    finally:
        handler.emit = original

    assert seen, "لم يمر أي سجل إلى المعالج"
    assert threading.get_ident() not in seen, "الكتبت من خيط الطلب نفسه"


def test_dropped_counter_is_exposed(app):
    assert isinstance(logging_setup.dropped_count(), int)


def test_root_logger_does_not_propagate(app):
    assert logging.getLogger("app").propagate is False


def test_get_logger_prefixes_to_app(app):
    assert logging_setup.get_logger("news").name == "app.news"
    assert logging_setup.get_logger("app.editor").name == "app.editor"


def test_waitress_ident_is_latin1_safe():
    """waitress writes ident into the Server response header (latin-1 only).

    An Arabic ident raised UnicodeEncodeError on every single response, so
    run.py must keep it ASCII.
    """
    import ast

    source = (Path(__file__).resolve().parent.parent / "run.py").read_text(encoding="utf-8")
    idents = [
        ast.literal_eval(kw.value)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "serve"
        for kw in node.keywords
        if kw.arg == "ident"
    ]
    assert idents, "serve() must declare an ident"
    for value in idents:
        assert value.isascii(), f"waitress ident must be latin-1 safe: {value!r}"
        value.encode("latin-1")


def test_log_dir_is_isolated_from_the_app_runtime_log(app):
    """The suite must not write into logs/, the running app's log.

    AI tests inject deliberate ValueErrors on purpose; without isolation
    those stack traces land in logs/app.log and make the runtime log
    unusable for inspection.
    """
    from tests.conftest import TEST_LOG_DIR

    runtime_log_dir = (Path(__file__).resolve().parent.parent / "logs").resolve()
    assert Path(app.config["LOG_DIR"]).resolve() == Path(TEST_LOG_DIR).resolve()
    assert Path(app.config["LOG_DIR"]).resolve() != runtime_log_dir
    assert Path(app.config["LOG_FILE"]).name == "test.log"


def test_shutdown_is_idempotent(app):
    """الإغلاق مرتين لا يجوز أن يرمي."""
    listener = logging_setup._listener
    assert listener is not None
    logging_setup.shutdown_logging()
    assert logging_setup._listener is None
    logging_setup.shutdown_logging()
    # نعيد التهيئة حتى لا تتأثر بقية الاختبارات
    logging_setup._listener = listener
