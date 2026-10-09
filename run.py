"""نقطة تشغيل التطبيق محلياً عبر waitress."""
from __future__ import annotations

import logging
import os
import sys

from waitress import serve

from app import create_app
from app.core.logging_setup import shutdown_logging

app = create_app(os.getenv("FLASK_CONFIG"))


def main() -> int:
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    log = logging.getLogger("app.server")
    log.info("server.start url=http://%s:%s", host, port)
    print(f"\n  الموقع يعمل على:  http://{host}:{port}\n  لوحة التحرير:    http://{host}:{port}/auth/login\n")
    try:
        serve(app, host=host, port=port, threads=6, ident="nassa-news")
    except KeyboardInterrupt:
        log.info("server.stopped_by_keyboard")
    finally:
        shutdown_logging()
    return 0


if __name__ == "__main__":
    sys.exit(main())
