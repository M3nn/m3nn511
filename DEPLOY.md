# النشر على استضافة — دليل كامل

نقطة الدخول للخوادم (WSGI) هي **`run:app`** (الوحدة `run.py` تحتوي `app`).
قاعدة البيانات SQLite داخل `instance/app.db`، وكل الكاش يُكتب في `instance/`
و`logs/` — **يجب أن يكونا قابلَي الكتابة** على الخادم.

> **قبل أي نشر حقيقي:**
> 1. غيّر `SECRET_KEY` إلى قيمة طويلة عشوائية:
>    `.venv\Scripts\python.exe -c "import secrets;print(secrets.token_urlsafe(48))"`
> 2. غيّر كلمات مرور الحسابات التجريبية (`admin/admin123`…) — انظر أدناه.

---

## 1) استضافة مشتركة cPanel (تُدعم Python App)

1. ارفع ملفات المشروع (من GitHub أو عبر اللوحة) إلى مجلد مثل `~/nassr`
   وحافظ على `instance/` كما هي (قاعدة البيانات والكاش).
2. **cPanel ⭢ Setup Python App ⭢ Create Application**:
   | الحقل | القيمة |
   |---|---|
   | Python version | 3.11 أو 3.12 |
   | Application root | `nassr` |
   | Application URL | دومينك أو subdomain |
   | **Application startup file** | `run.py` |
   | **Application entry point** | `app` |
3. من **Terminal** تثبّت التبعيات:
   ```bash
   cd ~/nassr
   source venv/bin/activate    # البيئة التي أنشأتها cPanel
   pip install -r requirements.txt
   ```
4. إن لم ترفع `instance/app.db` المليئة، أنشئ الجداول وعبّئ التجربة:
   ```bash
   flask --app run init-db
   flask --app run seed        # غيّر كلمات المرور في app/seed.py أولاً!
   ```
5. أنشئ `.env` من `.env.example` وعدّل `SECRET_KEY` (والاختياري `OPENAI_API_KEY`).
6. جهّز كاش الدوري مسبقاً: `flask --app run fetch-league`
7. **Restart** من صفحة Python App.

> cPanel تولّد `passenger_wsgi.py` تلقائياً؛ والملف المرفق `passenger_wsgi.py`
> يدعم العروض الأخرى التي تستخدمه حرفياً.

---

## 2) VPS (Ubuntu + Nginx) — تحكم كامل

```bash
sudo apt update && sudo apt install -y python3.12 python3.12-venv nginx
cd /opt && sudo git clone https://github.com/M3nn/m3nn511.git nassr
cd nassr && sudo chown -R $USER:$USER /opt/nassr

python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env            # ثم عدّل SECRET_KEY وغيره
flask --app run init-db
flask --app run fetch-league
```

خدمة دائمة `/etc/systemd/system/nassr.service`:

```ini
[Unit]
Description=Al-Nassr news platform
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/nassr
EnvironmentFile=/opt/nassr/.env
ExecStart=/opt/nassr/venv/bin/gunicorn --bind 127.0.0.1:8000 --workers 3 run:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now nassr
```

Nginx `/etc/nginx/sites-available/nassr`:

```nginx
server {
    listen 80;
    server_name nassr.example.com;

    location /static/ {
        alias /opt/nassr/app/static/;
        expires 30d;
    }
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

ثم HTTPS: `sudo certbot --nginx -d nassr.example.com`

---

## 3) Render — نشر تلقائي من GitHub

أسرع خيار، يعيد النشر عند كل `git push`:

1. اربط المستودع `M3nn/m3nn511` بـ Render.
2. **New ⭢ Blueprint ⭢ اختر المستودع** — الملف `render.yaml` المضاف يعمل
   كل الإعدادات (البناء، أمر التشغيل، `SECRET_KEY` توليد تلقائي).
3. أو يدوياً **New ⭢ Web Service**:
   - Environment: **Python 3**
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn --bind 0.0.0.0:$PORT run:app`
   - أضف متغير `SECRET_KEY`. اختياري: `OPENAI_API_KEY`.

الموقع مجاني مع إيقاف تلقائي عند الخمول — أول زيارة بطيئة قليلاً ثم تعود.

---

## 4) PythonAnywhere

1. **Consoles ⭢ Bash**:
   ```bash
   git clone https://github.com/M3nn/m3nn511.git
   cd m3nn511
   python3.11 -m venv venv && source venv/bin/activate
   pip install -r requirements.txt
   flask --app run init-db
   ```
2. `instance/` في مجلد المشروع قابل للكتابة تلقائياً.
3. **Web ⭢ Add web app** (Manual config) ⭢ عدّل `wsgi.py` إلى:
   ```python
   from run import app as application
   ```
4. ضع `.env` في جذر المشروع، وحدّث `SECRET_KEY`.

---

## متغيرات بيئة مهمة

| المتغيّر | القيمة الموصى بها في الإنتاج |
|---|---|
| `SECRET_KEY` | **إلزامي** — عشوائي طويل، ثابت بين عمليات إعادة التشغيل |
| `OPENAI_API_KEY` | اختياري — غيابه يعطّل ميزتي AI فقط |
| `LEAGUE_ENABLED` | `1` (أو `0` إن كانت الاستضافة تحجب ESPN) |
| `LOG_LEVEL` | `INFO` (إنتاج) أو `WARNING` (أقل ضجيجاً) |

## قائمة الفحص النهائية (production checklist)

- [ ] `SECRET_KEY` جديد في `.env` — لا القيمة الافتراضية.
- [ ] كلمات مرور الحسابات التجريبية استُبدلت — استخدم `change_passwords.py`:
      `python change_passwords.py admin` (كلمة المرور تُدخل بطلب آمن، لا تمر على
      سجل المحطة). (`admin/admin123` مذكورة في README — عدّها مُخترَقة فوراً.)
      من الأفضل حذف الملف من الخادم بعد الاستخدام.
- [ ] `instance/` و`logs/` قابلان للكتابة، وملف `.env` **لن** يصل للـ git
      (متجاهل في `.gitignore`).
- [ ] HTTPS مفعّل، و`X-Frame-Options` قائمة تلقائياً (تُضاف في كل استجابة).
- [ ] `flask --app run fetch-league` شُغّل مرة بعد التركيب (يُخزّن الكاش).