"""اختبارات الموقع العام — الرئيسية، التصنيف، الخبر، البحث، الترقيم."""

from __future__ import annotations

from app.extensions import db
from app.models import Article, ArticleStatus
from tests.conftest import login


def test_home_returns_rtl_arabic_page(client, article):
    r = client.get("/")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'dir="rtl"' in body
    assert 'lang="ar"' in body
    assert "<title>" in body


def test_home_lists_published_article(client, article):
    assert article.title in client.get("/").get_data(as_text=True)


def test_home_hides_draft(client, article, draft):
    body = client.get("/").get_data(as_text=True)
    assert article.title in body
    assert draft.title not in body


def test_category_page_filters_by_category(client, article, category):
    r = client.get(f"/category/{category.slug}")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert article.title in body
    assert category.name in body


def test_public_page_size_comes_from_config(client, app, category):
    """ITEMS_PER_PAGE is the single knob for public pagination."""
    app.config["ITEMS_PER_PAGE"] = 2
    for i in range(1, 6):
        art = Article(
            title=f"خبر اختباري رقم {i} لقياس حجم الصفحة",
            body="متن كافٍ وطويل بما يكفي للنشر. " * 6,
            category_id=category.id,
            status=ArticleStatus.PUBLISHED,
        )
        art.regenerate_slug()
        art.published_at = art.created_at
        db.session.add(art)
    db.session.commit()

    # صفحة التصنيف تعرض كل عناصر الصفحة، بطاقة لكل عنصر
    r = client.get(f"/category/{category.slug}")
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert body.count('<article class="card') == 2
    assert "شاهد المزيد" in body  # زر المزيد يظهر لأن المجموع أكبر من حجم الصفحة

    app.config["ITEMS_PER_PAGE"] = 12

    body2 = client.get(f"/category/{category.slug}").get_data(as_text=True)
    assert body2.count('<article class="card') == 5
    assert "شاهد المزيد" not in body2


def test_unknown_category_is_404(client, app):
    assert client.get("/category/no-such-category").status_code == 404


def test_article_page_shows_title_body_and_summary(client, article):
    r = client.get(f"/article/{article.slug}")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert article.title in body
    assert article.summary in body


def test_article_page_404_for_unknown_slug(client, app):
    assert client.get("/article/no-such-article").status_code == 404


def test_draft_is_not_reachable_by_public_url(client, draft):
    assert client.get(f"/article/{draft.slug}").status_code == 404


def test_search_matches_title(client, article):
    assert article.title in client.get("/search?q=النصر").get_data(as_text=True)


def test_search_matches_body(client, article):
    assert article.title in client.get("/search?q=الديربي").get_data(as_text=True)


def test_search_with_no_results(client, article):
    r = client.get("/search?q=كلمة-غير-موجودة-xyz")
    assert r.status_code == 200
    assert article.title not in r.get_data(as_text=True)


def test_search_empty_query_is_ok(client, app):
    assert client.get("/search").status_code == 200
    assert client.get("/search?q=").status_code == 200


def test_pagination_splits_results(client, app, users, category):
    for i in range(1, 16):
        art = Article(
            title=f"خبر تجريبي رقم {i} لاختبار تقسيم الصفحات",
            body="متن تجريبي طويل بما يكفي لاجتياز الحد الأدنى للأحرف المطلوبة.",
            status=ArticleStatus.PUBLISHED,
            category_id=category.id,
            author_id=users["editor"].id,
        )
        art.regenerate_slug()
        art.published_at = art.created_at
        db.session.add(art)
    db.session.commit()

    p1 = client.get("/?page=1").get_data(as_text=True)
    p2 = client.get("/?page=2").get_data(as_text=True)
    assert p1 != p2


def test_pagination_clamps_out_of_range_page(client, article):
    assert client.get("/?page=9999").status_code == 200
    assert client.get("/?page=abc").status_code == 200
    assert client.get("/?page=-3").status_code == 200


def test_security_headers_present(client, article):
    r = client.get("/")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "SAMEORIGIN"


def test_static_css_is_served(client, app):
    r = client.get("/static/css/app.css")
    assert r.status_code == 200
    assert "--gold-500" in r.get_data(as_text=True)


def _rule_body(css: str, selector: str) -> str:
    """Declarations of the first rule whose selector is exactly `selector`.

    Skips pseudo and descendant matches (e.g. `.btn.gold:hover` for `.btn.gold`).
    """
    i = css.find(selector)
    while i != -1:
        rest = css[i + len(selector):]
        if rest.lstrip().startswith("{"):
            end = rest.index("}")
            return rest[rest.index("{") + 1:end]
        i = css.find(selector, i + 1)
    return ""


def test_footer_carries_the_copyright_notice(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "\u062c\u0645\u064a\u0639 \u0627\u0644\u062d\u0642\u0648\u0642" in body
    assert "\u0645\u0646\u0635\u0629 \u0623\u062e\u0628\u0627\u0631 \u0627\u0644\u0646\u0635\u0631" in body
    assert "2020-2026" in body
    assert "\u0646\u0645\u0648\u0630\u062c \u062a\u0639\u0644\u064a\u0645\u064a" not in body


GOLD_SURFACES = (".searchbar button", ".cta", ".btn.gold", ".mini.gold", ".s-doing")


def test_gold_palette_defines_a_specular_gradient(client):
    css = client.get("/static/css/app.css").get_data(as_text=True)
    for token in ("--gold-200", "--gold-600", "--gold-grad", "--gold-gloss"):
        assert token in css, token


def test_gold_surfaces_are_filled_with_the_gradient_not_flat(client):
    css = client.get("/static/css/app.css").get_data(as_text=True)
    for selector in GOLD_SURFACES:
        block = _rule_body(css, selector)
        assert block, f"rule not found: {selector}"
        assert "var(--gold-grad)" in block, selector
        assert "background: var(--gold-500)" not in block, selector


def test_gold_controls_carry_a_specular_gloss_overlay(client):
    css = client.get("/static/css/app.css").get_data(as_text=True)
    assert ".btn.gold::after" in css
    assert ".cta::after" in css
    assert "var(--gold-gloss)" in css
    assert ".mini.gold::after" in css, "the gloss covers the gold controls only"


def test_brand_mark_takes_its_size_from_the_supplied_artwork(client):
    """The crest is a bitmap, so the box follows the file instead of a fixed square."""
    css = client.get("/static/css/app.css").get_data(as_text=True)
    block = _rule_body(css, ".brand-mark")
    assert "height: 80px" in block
    assert "width: auto" in block, "the box must follow the file's aspect ratio"
    assert "position: relative" not in block, "nothing overlays the artwork any more"


def _hue(value: str) -> float:
    """HSL hue in degrees for a #rrggbb string."""
    import colorsys

    r, g, b = (int(value[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return colorsys.rgb_to_hls(r, g, b)[0] * 360


def _luma(value: str) -> float:
    """WCAG relative luminance for a #rrggbb string."""
    out = []
    for i in (1, 3, 5):
        c = int(value[i:i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]


def test_gold_tokens_stay_gold_and_never_turn_green(client):
    """Pure gold lives at hue 38-45deg; past that a yellow reads olive/green."""
    import re

    css = client.get("/static/css/app.css").get_data(as_text=True)
    tokens = dict(re.findall(r"(--gold-\d+):\s*(#[0-9a-fA-F]{6})", css))
    assert len(tokens) == 5, sorted(tokens)
    for name, value in sorted(tokens.items()):
        hue = _hue(value)
        assert 38 <= hue <= 45, f"{name} {value} hue {hue:.1f} is not pure gold"


def test_navy_text_on_gold_stays_legible(client):
    """Retuning the ramp must never cost contrast on the gold-filled controls."""
    import re

    css = client.get("/static/css/app.css").get_data(as_text=True)
    navy = re.search(r"--navy-900:\s*(#[0-9a-fA-F]{6})", css).group(1)
    tokens = dict(re.findall(r"(--gold-\d+):\s*(#[0-9a-fA-F]{6})", css))
    for name in ("--gold-500", "--gold-400", "--gold-300"):
        a, b = _luma(tokens[name]), _luma(navy)
        ratio = (max(a, b) + 0.05) / (min(a, b) + 0.05)
        assert ratio >= 4.5, f"navy on {name} {tokens[name]} is only {ratio:.2f}:1"


def test_brand_reads_the_platform_name_on_one_line(client):
    """The header brand and the footer notice must be the same single name."""
    body = client.get("/").get_data(as_text=True)
    assert "منصة أخبار النصر" in body
    assert "نصّة" not in body, "the old brand still ships somewhere"

    import re

    i = body.index('class="brand-text"')
    region = body[i:body.index("</a>", i)]
    text = re.sub(r"<[^>]+>", " ", region)
    assert "منصة أخبار النصر" in " ".join(text.split()), "brand must read as one name"

    title = body[body.index("<title>"):body.index("</title>")]
    assert "منصة أخبار النصر" in title


def test_brand_lead_word_is_the_platform_word_in_its_own_span(client):
    """"منصة" must be separately addressable so it can be styled apart."""
    body = client.get("/").get_data(as_text=True)

    i = body.index('class="brand-lead"')
    tag = body[body.rindex("<", 0, i):body.index(">", i) + 1]
    assert "<span" in tag, tag

    inner = body[body.index(">", i) + 1:body.index("</span>", i)]
    assert inner.strip() == LEAD, inner

    after = body[body.index("</span>", i) + len("</span>"):]
    assert " ".join(after.split()).startswith('<span class="brand-sub">'), \
        "the subtitle must follow immediately so `+ brand-sub` can reach it"


def test_brand_lead_word_uses_its_own_display_typeface(client):
    """The lead word must not be set in the same face as the rest of the site."""
    import re

    css = client.get("/static/css/app.css").get_data(as_text=True)
    lead = _rule_body(css, ".brand-lead")
    assert lead, ".brand-lead must be styled"

    site = re.search(r"font-family:\s*([^;]+);", _rule_body(css, "body")).group(1)
    face = re.search(r"font-family:\s*([^;]+);", lead).group(1)

    assert face != site, "the lead word must differ from the site typeface"
    assert '"Segoe UI"' not in face, "that is the site's own first choice"
    assert "Tahoma" not in face.split(",")[0], "the fallback must not lead"

    # 800 resolves to the family's real Bold instead of smearing the glyphs
    weight = int(re.search(r"font-weight:\s*(\d+)", lead).group(1))
    assert weight >= 800, f"{weight} is not as heavy as the family allows"

    base = float(re.search(r"font-size:\s*([\d.]+)rem",
                           _rule_body(css, ".brand-text")).group(1))
    lead_size = float(re.search(r"font-size:\s*([\d.]+)em", lead).group(1))
    assert lead_size > 1, f"{lead_size}em does not stand above the {base}rem brand"


def test_brand_lead_word_turns_white_and_the_subtitle_gilds_on_hover(client):
    """"منصة" whitens as the pointer rests on it, while "أخبار النصر" gilds."""
    import re

    css = client.get("/static/css/app.css").get_data(as_text=True)

    resting = re.search(r"color:\s*([^;]+);",
                        _rule_body(css, ".brand-sub")).group(1)
    assert "#fff" in resting, "the subtitle rests white over the dark header"

    lead = _rule_body(css, ".brand-text:has(.brand-lead:hover) .brand-lead")
    assert lead, "no hover rule turns the lead word white"
    assert re.search(r"color:\s*#fff\s*;", lead), lead

    sub = _rule_body(css, ".brand-text:has(.brand-lead:hover) .brand-sub")
    assert "var(--gold-400)" in sub, "hovering the lead gilds the subtitle"


def test_brand_mark_adds_no_plate_behind_the_real_crest(client):
    """A gold disc or a circle clip would fight the artwork's own outline."""
    css = client.get("/static/css/app.css").get_data(as_text=True)
    block = _rule_body(css, ".brand-mark")
    assert "clip-path" not in block
    assert "border-radius" not in block, "the artwork carries its own shape"
    assert "var(--gold-grad)" not in block, "no gold plate behind real artwork"
    assert "background" not in block


def test_search_submit_sits_inside_the_field_at_the_rtl_start(client):
    """The submit affordance belongs inside the input, on the right in RTL."""
    css = client.get("/static/css/app.css").get_data(as_text=True)

    bar = _rule_body(css, ".searchbar")
    assert "position: relative" in bar, "the field cannot host an inside button"

    btn = _rule_body(css, ".searchbar button")
    assert "position: absolute" in btn
    assert "inset-inline-start" in btn, "must sit on the right-hand RTL start edge"
    assert "var(--gold-grad)" in btn

    inp = _rule_body(css, ".searchbar input")
    assert "padding-inline-start" in inp, "text would run under the inside icon"
    assert "border-radius: 999px" in inp, "field must be a fully-rounded pill"


def test_search_button_is_an_icon_with_an_accessible_name(client):
    """No bare text label; an inline svg plus aria-label instead."""
    body = client.get("/").get_data(as_text=True)
    i = body.index('class="searchbar"')
    snippet = body[i:body.index("</form>", i)]
    assert "<svg" in snippet
    assert 'aria-label=' in snippet
    assert ">{0}</button>".format("\u0628\u062d\u062b") not in snippet


def test_gloss_layer_never_overrides_the_inside_search_button(client):
    """A later equal-specificity `position` rule would detach the icon button."""
    import re

    css = client.get("/static/css/app.css").get_data(as_text=True)
    declared = []
    for rule in re.findall(r"\.searchbar button[^{]*\{[^}]*\}", css):
        position = re.search(r"position:\s*(\w+)", rule)
        if position:
            declared.append((rule, position.group(1)))
    assert declared, "the icon button must be absolutely positioned"
    for rule, value in declared:
        assert value == "absolute", rule


def test_crest_gets_no_synthetic_gloss_over_real_artwork(client):
    """The png already carries its highlights; a white overlay washes them out."""
    css = client.get("/static/css/app.css").get_data(as_text=True)
    assert ".brand-mark::after" not in css, "no gloss layer on the bitmap crest"
    assert ".brand-mark::before" not in css


def test_brand_mark_is_the_supplied_crest_file_not_a_drawn_shape(client):
    """The club crest is the attached bitmap, referenced as a static file."""
    body = client.get("/").get_data(as_text=True)
    i = body.index('class="brand-mark"')
    tag = body[body.rindex("<", 0, i):body.index(">", i) + 1]

    assert "<img" in tag, tag
    assert "/static/img/nassr-logo.png" in tag
    assert 'alt="' + ALT + '"' in tag, "the crest needs a text alternative"
    assert 'width="640"' in tag and 'height="640"' in tag, \
        "declare the intrinsic size so the header does not shift"


def test_crest_image_is_served_at_full_colour_depth_and_its_own_hash(client):
    """The artwork must stay high quality: 8-bit RGBA, not interlaced.

    The supplied 1024x820 PNG is trimmed to its square crest (618x618),
    given a small even margin, and exported as a 640x640 RGBA bitmap.
    """
    import hashlib
    import struct

    resp = client.get("/static/img/nassr-logo.png")
    assert resp.status_code == 200
    blob = resp.data

    assert blob[:8] == b"\x89PNG\r\n\x1a\n"
    w, h, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", blob[16:29])
    assert (w, h) == (640, 640), "the trimmed, squared crest"
    assert (depth, color, interlace) == (8, 6, 0), "8-bit RGBA, not interlaced"
    assert hashlib.sha256(blob).hexdigest() == LOGO_SHA, "the crest was re-encoded"


LEAD = "منصة"  # منصة
ALT = "النصر السعودي"  # النصر السعودي
LOGO_SHA = "4dca2885bab90ad0430c8997b05b99e5619b4ef7ee9328a8ea9439d9565ca36b"  # sha256 of app/static/img/nassr-logo.png
HOME = "الرئيسية"  # الرئيسية


def test_search_sits_after_every_category_in_the_nav_strip(client, category):
    """Search moved to the tail of the strip, past the last category link."""
    body = client.get("/").get_data(as_text=True)

    start = body.index("cats-inner")
    cats = body[start:body.index("</header>", start)]

    assert 'class="searchbar"' in cats, "search must live in the nav strip"
    search = cats.index('class="searchbar"')
    last_cat = cats.rindex("/category/")

    assert cats.index(HOME) < last_cat, "the home link stays first"
    assert last_cat < search, "search must come after the categories"
    assert cats[last_cat:search].count("<a ") == 0, "no link may follow the field"


def test_search_is_set_off_from_the_last_category_by_a_moderate_gap(client):
    """Neither flush against the pills nor stranded in a section of its own."""
    import re

    css = client.get("/static/css/app.css").get_data(as_text=True)
    gap = float(re.search(r"gap:\s*([\d.]+)px", _rule_body(css, ".cats-inner")).group(1))
    margin = re.search(r"margin-inline-start:\s*([\d.]+)px",
                       _rule_body(css, ".searchbar"))
    assert margin, "the field needs a gap from the last category"

    space = float(margin.group(1))
    assert space >= gap * 2, f"{space}px is too tight against a {gap}px nav gap"
    assert space <= 24, f"{space}px reads as a separate section"


def test_search_survives_an_empty_category_list(client, app):
    """Search must not depend on data: an empty nav still has to offer it."""
    with app.app_context():
        from app.models import Category
        from app.extensions import db

        for c in Category.query.all():
            db.session.delete(c)
        db.session.commit()

    body = client.get("/").get_data(as_text=True)
    assert 'class="searchbar"' in body, "search vanished with the categories"
    assert "cats-inner" in body


def test_search_input_is_smaller_than_the_navigation_text(client):
    """The user asked for a more compact field."""
    import re

    css = client.get("/static/css/app.css").get_data(as_text=True)
    inp = re.search(r"font-size:\s*([\d.]+)rem", _rule_body(css, ".searchbar input"))
    cats = re.search(r"font-size:\s*([\d.]+)rem", _rule_body(css, ".cats a"))
    assert inp and cats, "both sizes must be declared"
    assert float(inp.group(1)) < float(cats.group(1)), \
        f"search {inp.group(1)}rem must be smaller than nav {cats.group(1)}rem"


def test_search_bar_is_a_compact_inline_element_not_a_stretching_flex(client):
    """It must no longer claim the free width of the top bar."""
    css = client.get("/static/css/app.css").get_data(as_text=True)
    block = _rule_body(css, ".searchbar")
    assert "flex: 1" not in block, "the field must size to its content now"
    assert "min-width: 200px" not in block


# ============ تصميم الرئيسية: Hero + شبكة + شكل التصنيفات ============


def _publish(category, title: str) -> Article:
    art = Article(
        title=title,
        body="متن كافٍ وطويل بما يكفي للنشر في اختبار تصميم الرئيسية. " * 6,
        category_id=category.id,
        status=ArticleStatus.PUBLISHED,
    )
    art.regenerate_slug()
    art.published_at = art.created_at
    db.session.add(art)
    db.session.commit()
    return art


def test_home_hero_is_a_single_full_width_lead_story(client, article):
    """السلايدر الرئيسي شريحة كاملة العرض تحمل صورة الخبر وعنوانه."""
    body = client.get("/").get_data(as_text=True)
    assert 'class="news-slider"' in body
    assert 'class="slider-slide' in body
    assert 'class="hero-title"' in body
    assert article.title in body
    assert "hero-side" not in body, "لم يبقَ عمود جانبي من التصميم القديم"


def test_home_hero_image_fills_its_lead_card(client):
    """صورة شريحة السلايدر تغطي الشريحة كاملة (لا نصف عرض)."""
    css = client.get("/static/css/app.css").get_data(as_text=True)
    block = _rule_body(css, ".slider-img")
    assert "width: 100%" in block and "height: 100%" in block
    assert "object-fit: cover" in block


def test_home_remaining_articles_share_one_uniform_grid(client, article, category):
    """بعد الخبر الرئيسي، الباقي كلّه شبكة بطاقات متساوية."""
    _publish(category, "خبر ثانٍ يذهب إلى الشبكة الموحّدة")
    _publish(category, "خبر ثالث يذهب إلى الشبكة الموحّدة")
    body = client.get("/").get_data(as_text=True)
    assert 'class="grid"' in body
    assert "card-lg" not in body, "لا بطاقات جانبية كبيرة بعد الآن"


def test_home_categories_render_as_a_strip(client, category):
    body = client.get("/").get_data(as_text=True)
    assert 'class="cat-grid"' in body
    assert 'class="cat-card"' in body
    assert category.name in body


# ============ «شاهد المزيد» بدل الترقيم ============

def test_home_shows_thirteen_latest_with_a_see_more_button(client, category):
    """الرئيسية تعرض 13 شريحة سلايدر (كل أخبار الرئيسية) + 12 بطاقة وزر «شاهد المزيد» بلا سابق/التالي."""
    for i in range(16):
        _publish(category, f"خبر الرئيسية رقم {i} لعرض ثلاثة عشر عنصراً")
    body = client.get("/").get_data(as_text=True)
    assert body.count('<article class="card') == 12, "12 بطاقة في الشبكة"
    assert body.count('class="slider-slide') == 13, "شرائح السلايدر = كل أخبار الرئيسية = 13"
    assert "شاهد المزيد" in body
    assert "hx-swap=\"beforeend\"" in body
    assert ">التالي<" not in body and ">السابق<" not in body


def test_home_see_more_partial_returns_cards_and_out_of_band_button(client, category):
    """طلب الدفعة التالية يرجع البطاقات فقط + زر جديد بـ hx-swap-oob."""
    for i in range(16):
        _publish(category, f"خبر المزيد رقم {i} لاختبار الدفعة التالية")
    r = client.get("/?page=2&partial=1")
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "<!doctype" not in body.lower()
    assert "<html" not in body.lower()
    assert '<article class="card' in body
    assert 'hx-swap-oob="true"' in body
    assert 'id="see-more-slot"' in body


def test_category_see_more_partial_returns_cards(client, category):
    for i in range(16):
        _publish(category, f"خبر التصنيف رقم {i} لاختبار المزيد")
    body = client.get(f"/category/{category.slug}?page=2&partial=1").get_data(as_text=True)
    assert "<!doctype" not in body.lower()
    assert '<article class="card' in body
    assert 'id="see-more-slot"' in body


def test_see_more_button_matches_the_reference_style(client, category):
    css = client.get("/static/css/app.css").get_data(as_text=True)
    assert ".see-more-arrow" in css
    assert "color: #757575" in css, "النص رمادي كما في المرجع"
    for i in range(16):
        _publish(category, f"خبر نمط المرجع رقم {i} لاختبار الزر")
    body = client.get("/").get_data(as_text=True)
    assert "see-more-arrow" in body


# ============ رسالة الموقع الفارغ: للمدير وحده ============

SEED_HINT = "flask seed"


def test_home_hides_the_seed_hint_from_visitors(client, users):
    body = client.get("/").get_data(as_text=True)
    assert SEED_HINT not in body
    assert "لا توجد أخبار منشورة" not in body


def test_home_hides_the_seed_hint_from_a_writer(client, users):
    login(client, "writer", "writer123")
    body = client.get("/").get_data(as_text=True)
    assert SEED_HINT not in body
    assert "لا توجد أخبار منشورة" not in body


def test_home_hides_the_seed_hint_from_an_editor(client, users):
    login(client, "editor", "editor123")
    body = client.get("/").get_data(as_text=True)
    assert SEED_HINT not in body


def test_home_shows_the_seed_hint_to_the_admin(client, users):
    login(client, "admin", "admin123")
    body = client.get("/").get_data(as_text=True)
    assert SEED_HINT in body
