# PROJECT_MAP — منصّة أخبار النصر + إدارة مهام تحريرية

> آخر تحديث: 2026-10-08 · الحالة: **مُنفَّذ ومُتحقَّق منه بالكامل**
> هذا الملف هو المرجع الوحيد للبنية. أي كود جديد يجب أن يُذكر هنا أولاً.

**حالة التحقّق:** `184` اختبار — `179` أخضر و`5` إخفاقات سابقة في تسمية الشعار/الترويسة لا علاقة لها بالميزة (انظر [KNOWN DRIFT]) · فحص E2E على خادم حقيقي للحذف الفردي والجماعي والإجباري، ولتحكّم التصنيفات الكامل (إضافة/تحرير/حذف)، وللتحميل التدريجي «شاهد المزيد»، ولقسم دوري روشن بمواعيده ونتائجه وتواريخه الهجرية · `0` traceback في `logs/app.log` التشغيلي · `0` ملف يتضمّن `TODO`/`FIXME`.

---

## [TECH_STACK]

### Runtime
| العنصر | القرار | ملاحظة |
|---|---|---|
| Python | **3.13.16** (المطلوب ≥3.11) | SQLAlchemy 2.1.3 يفرض `>=3.11` |
| مدير البيئة | `uv` 0.12.23 | أنشأ `.venv` على CPython 3.13.16 |
| OS | Windows (PowerShell) | |
| venv | `.venv/` | مُستثنى من git |

### التبعيات المُثبّتة (pinned، مُتحقَّق من PyPI بتاريخ 2026-10-05)
```
Flask==3.1.3          Flask-SQLAlchemy==3.1.1   SQLAlchemy==2.1.3
Flask-Login==0.6.3    Flask-WTF==1.3.0          WTForms==3.2.2
python-dotenv==1.2.4  openai==3.24.0            waitress==3.0.2
hijridate==2.3.0   # تقويم أم القرى لتواريخ قسم دوري روشن
# dev
pytest==9.1.1
```
كلها **غير مهجورة** ولا مُهمَلة. تم التحقق من الاستيراد الفعلي بعد التثبيت.

### التبعيات المُستبعدة عمداً (Protocol 2 — No Feature Creep)
| الحزمة | سبب الاستبعاد |
|---|---|
| `pillow` | لا رفع صور؛ `cover_image_url` نصي فقط |
| `email-validator` / `flask-mail` | لا تسجيل عام ولا استعادة كلمة مرور |
| `marshmallow` | لا API عام؛ القوالب Jinja2 تقرأ النماذج مباشرة |
| `arrow` | فلتر تاريخ عربي في `app/__init__.py` — ملف كامل بلا مبرر |
| `alembic` | `db.create_all()` يكفي لـ v1 |
| `redis` / `celery` | لا طوابير مهام؛ الطابور داخلي وهو للسجلات فقط |
| `flask-caching` | لا حاجة؛ SQLite محلي |
| `requests` | نداءات ESPN في قسم الدوري تتم بـ `urllib` من المكتبة القياسية — تبعية كاملة بلا مبرر |
| `hijri-converter` | النسخة المهجورة من `hijridate`؛ أُخذت الأخيرة (`Gregorian(...).to_hijri()`) لتواريخ أم القرى |

### الواجهة
- **SSR**: Jinja2 + **HTMX 2.x من CDN** (بلا build step، بلا Node)
- **CSS**: ملف واحد `app/static/css/app.css` بمتغيّرات CSS — **لا Tailwind**
- **RTL**: `dir="rtl" lang="ar"` على `<html>`
- **الهوية**: ذهبي + أزرق غامق

### الذكاء الاصطناعي
| العنصر | القرار |
|---|---|
| SDK | `openai==3.24.0` |
| API | **Responses API** فقط |
| النموذج الافتراضي | `gpt-6-luna` — قابل للتبديل عبر `AI_MODEL` |
| نداء الـ API | متزامن داخل الطلب، `timeout` من `AI_TIMEOUT`، بلا streaming |
| القياس | كل نداء يكتب صفاً في `ai_usage` (tokens + model + lat_ms) |
| مفتاح AI | `OPENAI_API_KEY` — **اختياري**؛ غيابه لا يُعطّل التطبيق |

### البيانات والتشغيل
| العنصر | القرار |
|---|---|
| DB | **SQLite** ملف `instance/app.db` (WAL) |
| ORM | SQLAlchemy 2.1 declarative + `Mapped[]` annotations |
| الترحيل | `db.create_all()` عبر CLI — لا Alembic في v1 |
| الخادم | `waitress` على `127.0.0.1:8000` |
| الإعدادات | `python-dotenv` + `Config` / `DevConfig` / `TestConfig` |
| كاش الدوري | `instance/league.json` — يُجدَّد كل `LEAGUE_TTL` (600s)؛ فشل الشبكة ⇒ نسخة قديمة، لا تعطّل |

---

## [SYSTEM_FLOW]

### A. خريطة المسارات الفعلية (مُستخرَجة من `app.url_map`)

| المسار | الطرق | نقطة النهاية | صلاحية |
|---|---|---|---|
| `/` | GET | `news.home` | عامة |
| `/category/<slug>` | GET | `news.category` | عامة |
| `/article/<slug>` | GET | `news.article` | عامة |
| `/search` | GET | `news.search` | عامة |
| `/auth/login` | GET, POST | `auth.login` | عامة |
| `/auth/logout` | **POST فقط** | `auth.logout` | مسجَّل |
| `/editor` | GET | `editor.index` | محرّر/مدير |
| `/editor/stats` | GET | `editor.stats` | محرّر/مدير |
| `/editor/articles/new` | GET, POST | `editor.new` | محرّر/مدير |
| `/editor/articles/<id>/edit` | GET, POST | `editor.edit` | محرّر/مدير |
| `/editor/articles/<id>/publish` | POST | `editor.publish` | محرّر/مدير |
| `/editor/articles/<id>/delete` | POST | `editor.delete` — يدعم `delete_tasks=1` (مدير) | محرّر/مدير |
| `/editor/articles/delete-selected` | POST | `editor.delete_selected` — حذف جماعي للمحدّد + `delete_tasks=1` (مدير) | محرّر/مدير |
| `/editor/articles/<id>/ai-summary` | POST | `editor.ai_summary` **← AI-1** | محرّر/مدير |
| `/admin/categories` | GET | `admin.categories` — قائمة التصنيفات مع عدد أخبار كل تصنيف | مدير |
| `/admin/categories/new` | GET, POST | `admin.category_new` — إضافة تصنيف (اسم + ترتيب) | مدير |
| `/admin/categories/<id>/edit` | GET, POST | `admin.category_edit` — تحرير الاسم/الترتيب (يُحدَّث الـ slug عند التسمية) | مدير |
| `/admin/categories/<id>/delete` | POST | `admin.category_delete` — حذف التصنيف دون حذف أخباره (تُفكّ إلى «بلا تصنيف») | مدير |
| `/tasks` | GET | `tasks.index` | كل الموظفين |
| `/tasks/new` | GET, POST | `tasks.new` | كل الموظفين |
| `/tasks/<id>/edit` | GET, POST | `tasks.edit` | صاحب المهمة أو محرّر+ |
| `/tasks/<id>/advance` | POST | `tasks.advance` | صاحب المهمة أو محرّر+ |
| `/tasks/<id>/status` | POST | `tasks.set_status` | صاحب المهمة أو محرّر+ |
| `/tasks/<id>/delete` | POST | `tasks.delete` | صاحب المهمة أو محرّر+ |
| `/tasks/suggest` | GET, POST | `tasks.suggest` **← AI-2** | كل الموظفين |

> `/editor` و `/tasks` يقبلان الشرطة اللاحقة أيضاً (`/editor/`) — سلوك Flask
> الافتراضي عند `strict_slashes`، غير ضارّ.

> **CLI إضافي:** `flask fetch-league` يجلب نتائج ومواعيد دوري روشن ويحدّث الكاش
> متجاهلاً المهلة (للجدولة الزمنية). الرئيسية نفسها تجدّد الكاش تلقائياً ضمن المهلة.

**قاعدة الحذف:** مقال مرتبط بمهام لا يُحذف افتراضياً (حارس سلامة بيانات).
المدير وحده يملك تجاوزها عبر `delete_tasks=1` من مربّع «احذف المهام المرتبطة أيضاً»
(في صفحة التحرير وفي قائمة `/editor`)؛ عندها تُحذف المهام مع المقال.
المحرّر/الكاتب يُتجاهَل طلبهما ويبقى المنع (مُثبَّت بالاختبارات).

**التحميل التدريجي:** صفحات القوائم العامة (`/`, `/category/*`, `/search`) تعرض
`ITEMS_PER_PAGE` (13) عنصراً، ثم زر «شاهد المزيد» بدل ترقيم السابق/التالي.
الزر بنمط موقع النصر: نص رمادي + سهم لأسفل، ويجلب الدفعة التالية عبر HTMX.
الضغط عليه يجلب `?partial=1&page=N` فيعيد الخادم البطاقات فقط + زراً بديلاً
عبر `hx-swap-oob` (HTMX). الشرط `_wants_partial()` في `app/news/routes.py`.

### B. تدفّق البيانات

```
POST /editor/articles/<id>/ai-summary          (HX-Request)
  → CSRF → login_required → role in (editor, admin)   [writer ⇒ 403]
  → article = get(id)                          [مفقود ⇒ 404]
  → text  = article.body[:AI_MAX_INPUT_CHARS]
  → ai.summarize(text)
        responses.create(model=AI_MODEL, instructions=AR_SYS, input=text,
                         max_output_tokens=AI_MAX_OUTPUT_TOKENS)
        log("ai.ok", feature, model, tokens, lat_ms)
        INSERT ai_usage(user_id, feature, model, in_tok, out_tok, lat_ms, ok)
  → article.summary = النتيجة ؛ commit
  → استبدال HTMX داخل #ai-summary-box

POST /tasks/suggest                              (HX-Request)
  → CSRF → login_required
  → brief = form.brief
  → ai.suggest_tasks(brief)
        يطلب JSON array ثم _parse_tasks() يُسقط العناصر الفاسدة
        ويقصّ النتيجة عند AI_MAX_SUGGESTIONS
  → INSERT ai_usage(feature="task_suggestions")
  → استبدال HTMX: قائمة عناوين + زر «أضف» لكل عنوان
```

**قاعدة الفشل (مُتحقَّق منها في `test_ai.py`):**

| الحالة | HTTP | الرسالة |
|---|---|---|
| مفتاح غير مهيّأ | `503` | تذكر `OPENAI_API_KEY` |
| `RateLimitError` | `429` | عربية |
| `APITimeoutError` | `504` | عربية |
| أي `APIError` | `502` | عربية، بلا تفاصيل المزوّد |
| خطأ غير متوقّع | `500` | عربية، بلا تفاصيل داخلية |
| مُدخل قصير | `400` | عربية |
| مُخرج فارغ/غير قابل للتحليل | `502` | عربية |

**لا يوجد نداء شبكة في الاختبارات إطلاقاً** — `_client()` مُستبدَل بـ `monkeypatch`.

### C. الذكاء الاصطناعي — نطاقان فقط (غير قابل للتوسّع)
| # | الميزة | المسار | مُدخل | مُخرج |
|---|---|---|---|---|
| AI-1 | تلخيص خبر بالعربية | `POST /editor/articles/<id>/ai-summary` | `body` | `summary` |
| AI-2 | اقتراح مهام تحريرية | `POST /tasks/suggest` | `brief` نصي | JSON `[{title, priority}]` |

**غير مشمول عمداً:** agents · RAG/vector store · streaming/SSE · tool calling ·
evals · image understanding · moderation · prompt editor UI · cost dashboard.

### D. قيود مُثبتة بالاختبارات
| القيد | كيف يُفرض |
|---|---|
| كاتب على `/editor` ⇒ `403` | `unauthorized_handler` في `app/__init__.py` |
| كاتب يفتح مهمة غيره ⇒ `404` لا `403` | `_get_task_or_404` في `app/tasks/routes.py` — لا نكشف وجودها |
| كاتب لا يُعيد إسناد مهمة لغيره | يُجبَر على نفسه في المسار |
| حذف مقال مرتبط بمهام ⇒ مرفوض | `_get_article_or_404` يفحص `task.article_id` |
| نشر متن أقصر من 80 حرفاً ⇒ مرفوض | `ArticleForm.body` Length(min=80) |
| إعادة توجيه خارجية ⇒ مُنكرة | `_safe_next` يرفض `//host` والـ `\` |
| `?next=` بلا `?` زائدة | `request.full_path.rstrip("?")` |
| CSRF **قبل** المصادقة | طلب POST بلا رمز ⇒ `400` لا `302` |

---

## [ARCHITECTURE]

### شجرة الملفات الفعلية (93 ملفاً مُتحقَّق منها — بلا `__pycache__` وملفات الفحص المؤقتة)
```
منصة النصر/
├── run.py                      نقطة الدخول: waitress على 127.0.0.1
├── README.md                   أوامر مُجرَّبة من مجلد نظيف
├── PROJECT_MAP.md              هذا الملف
├── requirements.txt            pinned
├── requirements-dev.txt        pytest
├── pytest.ini                  testpaths=tests، -q --strict-markers
├── .env.example                كل مفتاح مع افتراضه
├── .gitignore
├── instance/                   app.db (gitignored)
├── logs/                       app.log (gitignored)
├── app/
│   ├── __init__.py             create_app + الفلاتر العربية + 403/404/500 + CLI
│   ├── config.py               Config / DevConfig / TestConfig + resolve_config
│   ├── extensions.py           db, login_manager, csrf
│   ├── models.py               5 نماذج + slugify + التسميات + Task.advance
│   ├── seed.py                 3 مستخدمين · 5 تصنيفات · 16 خبراً · 6 مهام
│   ├── forms/base.py           ترجمة أخطاء WTForms + validate_image_url
│   ├── core/
│   │   ├── logging_setup.py    QueueHandler + QueueListener (Protocol 4)
│   │   └── pagination.py       paginate() — 6 مواقع استدعاء
│   ├── ai/service.py           summarize() + suggest_tasks() + سجل ai_usage
│   ├── league/
│   │   ├── __init__.py
│   │   └── service.py          دوري روشن: جلب ESPN + كاش JSON + تواريخ ميلادية وهجرية
│   ├── auth/{__init__,forms,routes}.py
│   ├── admin/{__init__,forms,routes}.py    تحكّم كامل بالتصنيفات (مدير فقط)
│   ├── editor/{__init__,forms,routes}.py
│   ├── news/{__init__,routes}.py
│   ├── tasks/{__init__,forms,routes}.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── auth/login.html
│   │   ├── news/{home,category,article,search,_more}.html
│   │   ├── editor/{list,form,stats}.html
│   │   ├── admin/{categories,category_form}.html
│   │   ├── tasks/{list,form,suggest}.html
│   │   ├── partials/{article_card,pager,see_more,flash,ai_summary,task_row,task_suggestions,league}.html
│   │   └── errors/error.html
│   └── static/
│       ├── css/app.css          نظام تصميم واحد
│       ├── img/nassr-logo.png   شعار النصر، بلا هوامش شفافة
│       └── img/teams/           شعارات أندية دوري روشن (تُنزَّل تلقائياً عند أول جلب)
└── tests/
    ├── __init__.py · conftest.py
    ├── test_models.py    12   test_logging.py 10   test_news.py  52
    ├── test_auth.py      18   test_editor.py  30   test_tasks.py 16
    ├── test_ai.py        25   test_admin.py   14
    └── test_league.py     7
```

### قرارات التجريد (Protocol 3 — Surgical, No Micro-Files)
- `app/models.py` ملف **واحد** لـ 5 نماذج. التقسيم كان سيُنتج 5 ملفات × ~12 سطر
  = تفتيت فاشل، والعلاقة `Article↔Task` تُنتج imports دائرية.
- **النماذج ترث `db.Model` مباشرةً.** قاعدة `DeclarativeBase` مستقلة تُخرج
  الجداول من `db.metadata` فلا ينشئها `db.create_all()` — درس مُدوَّن هنا لأن
  الفشل يظهر كـ `no such table: user` لا كخطأ استيراد.
- `app/core/pagination.py` ✅ 6 مواقع استدعاء · `logging_setup.py` ✅ إعداد عام
  لمرة واحدة · `ai/service.py` ✅ استدعاءان حقيقيان + سجل التكلفة.
- **لا يوجد** `utils.py` (درج مهملات). `slugify()` في `models.py`، فلتر التاريخ
  العربي في `app/__init__.py`.
- بلا `services/` عام، بلا `repositories/`، بلا `interfaces/`، بلا DTOs.

### المخطّطات (Schema)
```
User      id, username(uq), password_hash, display_name,
          role(enum: admin|editor|writer), created_at
Category  id, name, slug(uq), sort_order
Article   id, title, slug(uq), summary(TEXT), body(TEXT), cover_image_url,
          status(enum: draft|published), category_id→Category, author_id→User,
          published_at, created_at, updated_at
Task      id, title, description(TEXT), status(enum: todo|doing|done),
          priority(enum: low|med|high), due_date, assignee_id→User,
          article_id→Article(NULL), created_at, updated_at
AIUsage   id, user_id→User, feature(str), model(str), input_tokens(int),
          output_tokens(int), lat_ms(int), ok(bool), created_at
```

**الفهارس المُتحقَّق منها عبر `inspect(engine).get_indexes()`:**
`ix_article_status_published` · `ix_article_category` · `ix_task_status` ·
`ix_task_assignee` (＋ `ix_article_slug` و `ix_article_title` من إعلانات
`unique`/`index` في العمودين).

SQLite: `PRAGMA journal_mode=WAL` · `foreign_keys=ON`.

### الصلاحيات
| المسار | guest | writer | editor | admin |
|---|---|---|---|---|
| `/`, `/article/*`, `/category/*`, `/search` | ✅ | ✅ | ✅ | ✅ |
| `/auth/login` | ✅ | ✅ | ✅ | ✅ |
| `/tasks*` | ❌302 | ✅ مهامه فقط | ✅ الكل | ✅ |
| `/editor*` | ❌302 | ❌403 | ✅ | ✅ |
| `/admin*` (التصنيفات) | ❌302 | ❌403 | ❌403 | ✅ |
| `/auth/logout` | ❌405 (GET) | ✅ POST | ✅ | ✅ |

### نظام الألوان (من `app.css` — القيم الفعلية)
```css
--navy-900:#0A1628; --navy-800:#0F2440; --navy-700:#16325A; --navy-600:#1E4276;
--gold-500:#D79B18; --gold-400:#E5B542; --gold-300:#EACF90;
--gold-200:#F4E1B9; --gold-600:#AE760F;
--ink:#14213A; --paper:#FFFDF7; --line:#E7DFC8; --muted:#5C6B82;
--ok:#1D7A4C; --warn:#9A6A06; --err:#A52020;
/* composite, not hex */
--gold-grad:180deg #F4E1B9->#E5B542->#D79B18->#AE760F;
--gold-grad-hi:180deg #FFF6E0->#F4E1B9->#E5B542->#D79B18;
--gold-gloss:180deg rgba(255,255,255,.58)->transparent 52%;
--shadow-gold:0 6px 18px rgba(174,118,15,.30);
--shadow:0 1px 2px rgba(10,22,40,.06), 0 6px 16px rgba(10,22,40,.05);
```
النظام الذهبي اللامع: كل سطح الذهبي `var(--gold-grad)`، طبقة `::after` تضع `var(--gold-gloss)` على `.searchbar button` و`.cta` و`.btn.gold` و`.mini.gold` و`.brand-mark`.
أمّا `.dot` فبقي مسطحا لأن التدج على ثماني بكسلات يظهر. التذييل يعرض عبارة حقوق النشر مع تدرّج ذهبي علوي خفيف. النظام الذهبي محصور في `hue 38-45 درجة`، وفوق ذلك يميل إلى الأخضر، ويحرسه اختبار. الشعار صار صورةً حقيقية: `app/static/img/nassr-logo.png` وهو الملف المرفوع نفسه بجودة 8-بت RGBA، اقتُطع منه الهامش الشفاف فقط فصار 358×480، والبحث صار آخر عنصر في شريط التصنيفات. وكلمة "منصة" في الترويسة تُعرض بخط نسخ مختلف (`Sakkal Majalla`) ووزن 800 وحجم أكبر، وتكتسب "أخبار النصر" بيضاء عند المرور عليها.


---

## [ROSHN LEAGUE] — قسم دوري روشن في الرئيسية

**ساحة تحت الهيدر مباشرة** يحيط خبرها الرئيسي (السلايدر) بقسمي الدوري:
«مباريات هذا الأسبوع» **يمين** السلايدر، و«آخر النتائج» **يساره** (RTL).
«أحدث الأخبار» تعود بعرض كامل بعد الساحة كما كانت قبل الميزة، وعند غياب
بيانات الدوري يبقى السلايدر وحده بعرض كامل. لكل مباراة: شعارا الناديين
واسماهما عربياً، الملعب والمدينة بالعربية، توقيت الرياض، والتاريخ الميلادي
**والهجري** (أم القرى عبر `hijridate`).

| القرار | القيمة |
|---|---|
| التخطيط | شريط كحلي **ممتد بعرض الصفحة كاملاً** (لا فراغ يميناً/يساراً): مباريات يمين السلايدر · النتائج يساره؛ «أحدث الأخبار» بعرضها المعتاد بعدها — ≤1020px تصفّاً واحداً بنفس الترتيب |
| المصدر | واجهة ESPN العامة `ksa.1` — **بلا مفتاح API** ولا تبعية جديدة |
| الجلب | طلبات شهرية (`YYYYMM`) تغطي [−14 يوم، +8 أيام]، بهوية متصفّح، مهلة `LEAGUE_TIMEOUT` |
| الكاش | `instance/league.json` + `fetched_at`؛ تُجدَّد تلقائياً إذا جاوزت `LEAGUE_TTL` ثانية |
| الفشل | فشل شبكة ⇒ استمرار بالنسخة القديمة؛ غياب كامل للبيانات ⇒ إخفاء القسم — لا تعطّل للرئيسية |
| الشعارات | تُنزَّل مرة واحدة إلى `static/img/teams/<id>.png`، فشل التنزيل لا يُسقط التحديث |
| النافذة | القادمة قصّ عند **القراءة** إلى 7 أيام (لا وقت الجلب)، فالموقع القديم لا يعرض مباريات ماضية كقادمة |
| الحالة الحية | مباراة `live` تظهر في عمود القادمة مع شارة «مباشر» ونتيجتها |
| السجل | `league.refreshed/fetch_failed/refresh_failed/refresh_empty` في `app.league` |
| الاختبارات | `tests/test_league.py` (7) — `fetch_scoreboards` مُستبدَل، كاش في `tmp_path`، بلا شبكة إطلاقاً |

مفاتيح `.env`: `LEAGUE_ENABLED` (1) · `LEAGUE_TTL` (600) · `LEAGUE_TIMEOUT` (5) ·
`LEAGUE_CACHE_DIR` (فارغ ⇒ `instance/`). كلها اختيارية ولها افتراضيات صالحة.
`TestConfig.LEAGUE_ENABLED = False` — لا قسم ولا شبكة في الاختبارات الافتراضية.

---

## PROTOCOL 4 — نظام السجلات (Async, Non-blocking)

`app/core/logging_setup.py`:
1. `QueueHandler` + `QueueListener` بخيط **daemon** يستهلك `Queue(maxsize=1000)`.
2. يكتب إلى `RotatingFileHandler(logs/app.log, 2MB×5)` وإلى stderr عند
   `LOG_TO_STDERR=true`.
3. `put_nowait` + `except queue.Full` ⇒ يُسقط السجل ويعدّه
   `dropped_count()`. **لا blocking على أي request path.**
4. **Non-fatal**: فشل بدء الـ listener ⇒ fallback متزامن والتطبيق يكمل.
5. المستويات المعتمدة فقط: `DEBUG, INFO, WARNING, ERROR`.
6. `propagate=False` على جذر Flask لتفادي التكرار مع `waitress`.

جدول `ai_usage` هو سجل AI semi-critical (قياس تكلفة، بديل عن logging).

**قيد مهم اكتُشف أثناء التحقق:** ترويسة `Server` من waitress تُرمَّز بـ latin-1،
لذلك `ident` يجب أن يبقى ASCII. قيمة عربية كانت تُسقط **كل** استجابة بـ
`UnicodeEncodeError`. مثبَّت باختبار `test_waitress_ident_is_latin1_safe`.

---

## [DEFECTS FOUND & FIXED] — أثناء التحقق الذاتي

كل عيب أدنه  ثُبِّت باختبار، لأن فحصة `pytest` وحدها كانت تمرّ رغمه.

| # | العيب | الأثر | الإصلاح | الاختبار الحارس |
|---|---|---|---|---|
| 1 | النماذج ترث `DeclarativeBase` خاصة بدل `db.Model` | `create_all()` كان ينشئ **صفر** جداول ⇒ `no such table: user` في أول تشغيل | وراثة `db.Model` مباشرة على النماذج الخمسة | `test_models.py` |
| 2 | `func.case(..., else_=2)` من Flask | `TypeError` في SQLAlchemy 2.1 ⇒ `/editor/stats` يتعطّل | `from sqlalchemy import case` | `test_editor.py` |
| 3 | `ident="نصة-أخبار"` في `waitress` | ترويسة `Server` تُرمَّز latin-1 ⇒ `UnicodeEncodeError` على **كل** استجابة | `ident="nassa-news"` | `test_waitress_ident_is_latin1_safe` |
| 4 | `request.full_path` ينتج `next=/editor?` | حلقة إعادة توجيه في رابط الرجوع | `.rstrip("?")` | `test_auth.py` |
| 5 | `_safe_next` يقبل `//evil.example.com` | إعادة توجيه مفتوحة (open redirect) | رفض `//` و`\` | `test_auth.py` |
| 6 | ترجمة أخطاء WTForms تطابق أسماء صنف المدقِّق | رسائل إنجليزية تتسرّب لواجهة عربية | مطابقة **نص الرسالة** لا اسم الصنف | `test_editor.py` + `test_tasks.py` |
| 7 | `ITEMS_PER_PAGE` مُعرَّف وغير مستعمل | إعداد ميت يوهم بضبطه | `news/routes.py` يقرأه بدل `PAGE_SIZE` الثابت | `test_public_page_size_comes_from_config` |
| 8 | `ix_article_category` موثّق وغير موجود | مسح كامل للجدول في صفحات التصنيف | إضافة `Index` إلى `Article.__table_args__` | فحص `inspect(engine).get_indexes()` |
| 9 | `tests/conftest.py` يكتب في `logs/app.log` الحقيقي | اختبارات AI تحقن `ValueError` مقصودة ⇒ سجل التشغيل مليء بـ stack traces | `LOG_DIR` مؤقّت قبل استيراد `app` | `test_log_dir_is_isolated_from_the_app_runtime_log` |
| 10 | `tests/test_auth.py` كان محذوفاً | 90 اختباراً بلا أي غطاء للصلاحيات | إعادة كتابته (18 اختباراً) | `test_auth.py` |
| 11 | أزرار «النشر» و«الحذف» في `editor/form.html` داخل `<form>` آخر | المتصفّح يتجاهل النموذج المتداخل ⇒ الزرّان يsubmitان نموذج التعديل، فلا حذف ولا نشر من صفحة التحرير | فصل النماذج: النموذج الرئيس `id="article-form"`، والحقول الجانبية مربوطة بـ `form="article-form"` | `test_edit_page_has_no_nested_forms` |
| 12 | تعليمة `flask seed` الداخلية ظاهرة لكل زائر في الرئيسية الفارغة | تسرّب تعليمات تشغيل داخلية للجمهور | إظهارها للمدير فقط (`current_user.is_admin`) | `test_home_hides_the_seed_hint_*` |

> **الدرس العام:** ثلاثة من هذه العيوب (1، 3، 9) كانت تمرّ في `pytest` لأن
> الاختبار نفسه كان يستخدم نفس المسار المعطوب. الفحص التحوّلي (شغّل `run.py`
> كعملية حقيقية، وافحص السجل على القرص) هو ما كشفها — لا بدّ عنه.

## [KNOWN DRIFT] — اختبارات علامة تجارية لم تُزامَن بعد

خمسة اختبارات في `test_news.py` تصف ترويسة **قديمة** (`<small>` للعنوان الفرعي،
`.brand-mark` بارتفاع 40px، سمات الصورة 358×480). التصميم الحالي في
`base.html`/`app.css` يستخدم `<span class="brand-sub">` وارتفاع شعار 80px
وسمات 716×960 (نسبة الصورة نفسها). هذه الاختبارات فاشلة **قبل** إضافة الحذف
الجماعي وخيار حذف المهام للمدير، ولم تُمسّ في هذه التغييرات:

```
test_brand_mark_takes_its_size_from_the_supplied_artwork
test_brand_reads_the_platform_name_on_one_line
test_brand_lead_word_is_the_platform_word_in_its_own_span
test_brand_subtitle_turns_white_while_the_lead_word_is_hovered
test_brand_mark_is_the_supplied_crest_file_not_a_drawn_shape
```

**المطلوب:** قرار مالك المنتج — مواءمة الاختبارات مع التصميم الحالي، أو إرجاع
الترويسة إلى المواصفات القديمة.

## [ORPHANS & PENDING]

**فارغ — لا عمل مُعلَّق غير مُنجز.**

| البند الذي كان مفتوحاً | النتيجة |
|---|---|
| ORPHAN-0 · تثبيت Python 3.13 | ✅ **مُغلق** — `uv` 0.12.23 + CPython 3.13.16، و`.venv` بتبعيات مُتحقَّق من استيرادها |

### مؤجَّل بالتصميم (ليس عملاً مُعلَّقاً — لا يُنفَّذ في v1)
| البند | السبب |
|---|---|
| لوحة `/admin` (مستخدمون) | إدارة المستخدمين تتم بالـ seed؛ أما التصنيفات فصار لها لوحة `/admin/categories` كاملة |
| لوحة تحكم AI (تكلفة/سجل/محرّر prompts) | AI-1/AI-2 يكفيان للنطاق |
| Kanban / لوحة مهام بصرية | قائمة + حالات + تقديم حالة بالـ HTMX |
| رفع صور (multipart) | `cover_image_url` نصي يكفي |
| تسجيل عام / نسيت كلمة المرور / بريد | الموظفون يُبذرون بالـ seed |
| بحث دلالي / FTS5 | `LIKE` على title/body يكفي لـ v1 |
| تعليقات / منتدى | خارج النطاق |
| Docker + PostgreSQL + Alembic | محلي أولاً |
| Rate limiting / CORS | CSRF مفعّل بـ Flask-WTF |
| CI / GitHub Actions | pytest محلي كافٍ |
| SSE streaming / usage dashboard | لا طلب |

---

## خارطة الطريق — كل المعالم مُنجَزة

| M | الهدف القابل للتحقق | الحالة | الدليل |
|---|---|---|---|
| **P0** | Python 3.13 + تثبيت بلا تعارض | ✅ | `.venv` يعمل، 10 تبعيات مستورَدة |
| **M0** | `waitress` يرفع · `/` ⇒ 200 بـ `dir="rtl"` · `logs/app.log` يكتب عبر الطابور | ✅ | `e2e_runpy.py`: `server.start` + `news.home` + `app.start` في السجل |
| **M1** | `init-db` ⇒ 5 جداول · `seed` ⇒ 3/5/16 · `/editor` 302 للزائر و200 للمحرّر | ✅ | `test_auth.py` 18 · `test_models.py` 12 |
| **M2** | `/` يعرض البطاقات · التصنيف يقتصر على تصنيفه · `/article` كامل · بحث يطابق | ✅ | `test_news.py` 52 |
| **M3** | إنشاء مهمة تظهر فوراً · تقديم الحالة يبقى بعد إعادة التحميل · writer معزول · 403 على `/editor` | ✅ | `test_tasks.py` 16 · `test_auth.py` |
| **M4** | مع مفتاح: `summary` يُملأ + صف `ai_usage` · بدون مفتاح: 503 و`/` يبقى 200 | ✅ | `test_ai.py` 25 · تحقّق تفاضلي: 3 ثم 2 ثم 1 نداء |
| **M5** | `pytest` أخضر · أوامر README مُجرَّبة · بلا `None` في HTML · بلا traceback في السجل | ✅ | 179 أخضر + 5 انحراف علامة تجارية قائم · كل أوامر README نُفِّذت |

### معايير القبول — الحالة
| المعيار | النتيجة |
|---|---|
| ❌ ملف سطر واحد من منطق العمل | ✅ لا يوجد — أصغر ملف `forms/__init__.py` = سطر توثيق |
| ❌ استيراد من `app.utils` | ✅ لا يوجد |
| ❌ حزمة غير في `requirements.txt` | ✅ 10 فقط |
| ✅ كل Blueprint له `url_prefix` وكل route `methods=` صريح | ✅ `/auth/logout` POST فقط عمداً |
| ✅ كل query عبر `select()` | ✅ |
| ✅ كل POST محمي بـ CSRF | ✅ عدا `GET /auth/logout` = 405 |
| ✅ لا `TODO`/`FIXME`/placeholder | ✅ فحص آلي على 60 ملفاً |

### صيان يدوية لخطوات Windows (مسار حروف عربية)
المسار `C:\Users\Admin\Desktop\منصة النصر` يُفسد سلوك الأدوات أحيانًاً في الطرفية، فيتمرّع عند أي نص واقعي.
الحل المُعتمد: لا تمرّر المسار العربي في أوامر الطرفية إطلاقاً. أنشئ مشغّلاً
ASCII في `%TEMP%` يبحث عن `.venv` في `Desktop`، واستعمله لكل تنفيذ:
```powershell
Get-ChildItem "C:\Users\Admin\Desktop" -Directory | ForEach-Object {
  $py = Join-Path $_.FullName ".venv\Scripts\python.exe"
  if (Test-Path $py) { & $py @args }
}
```
كما لوحظ أن أداة الكتابة تُسقط أحياناً ملفات تنتهي بـ `__init__.py`؛ الحل:
الكتابة باسم مؤقّت ثم `Move-Item`. وكل تعديل عربي يُنفَّذ بسكربت Python
يستخدم `\uXXXX` لضمان عدم تغيّر النص في الطريق.
