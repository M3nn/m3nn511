# أوامر تشغيل منصّات PaaS (Render/Railway/Fly…).
# gunicorn مضمن في requirements.txt؛ محلياً يستمر التشغيل عبر run.py (waitress).
web: gunicorn --bind 0.0.0.0:$PORT run:app --access-logfile - --error-logfile -