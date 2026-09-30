# Fix pass 2026-09-29 PM — T6 / T9 / T11 + visual gates
import json, os, sys, io, subprocess, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright
import jsonschema

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
BASE = "http://localhost:8791/fahras.html"
GALLERY = os.path.join(os.path.dirname(__file__), "gallery")
os.makedirs(GALLERY, exist_ok=True)
schema = json.load(open(os.path.join(ROOT, "schema", "annotation.schema.json"), encoding="utf-8"))

results = {}

def set_result(k, ok, note=""):
    results[k] = ("PASS" if ok else "FAIL", note)
    print(f"{k}: {'PASS' if ok else 'FAIL'} {note}")

def contrast_ratio(rgb1, rgb2):
    def lum(rgb):
        def chan(c):
            c = c / 255.0
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        r, g, b = rgb
        return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)
    l1, l2 = lum(rgb1) + 0.05, lum(rgb2) + 0.05
    return max(l1, l2) / min(l1, l2)

def parse_rgb(s):
    if not s:
        return None
    s = s.strip()
    # rgb()/rgba()
    if s.startswith("rgb"):
        try:
            nums = s[s.index("(") + 1:s.index(")")].split(",")
            return tuple(float(n) for n in nums[:3])
        except Exception:
            return None
    # color(srgb r g b) — values 0..1
    if "srgb" in s:
        try:
            inner = s[s.index("srgb") + 4:s.rindex(")")].strip()
            parts = [p for p in inner.replace(",", " ").split() if p]
            vals = [float(p) for p in parts[:3]]
            if max(vals) <= 1.0:
                vals = [v * 255.0 for v in vals]
            return tuple(vals)
        except Exception:
            return None
    return None

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)

    # ---- Desktop light: T6, methods, verse, review toolbar, T9, T11, fidelity ----
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light", locale="ar-SA")
    pg = ctx.new_page()
    pg.goto(BASE, wait_until="networkidle")
    pg.wait_for_timeout(600)

    fs = pg.evaluate("document.documentElement.getAttribute('data-fidelity-selftest')")
    n = pg.evaluate("document.documentElement.getAttribute('data-fidelity-n')")
    set_result("fidelity_selftest", str(fs).lower() == "pass" and str(n) == "12", f"selftest={fs} n={n}")

    # Methods one-line desktop
    wrap_info = pg.evaluate("""() => {
      const names = Array.from(document.querySelectorAll('#method-list .method-name'));
      return names.map(el => {
        const cs = getComputedStyle(el);
        const wraps = el.scrollHeight > el.clientHeight + 2 || el.getClientRects().length > 1;
        return {
          text: el.textContent,
          whiteSpace: cs.whiteSpace,
          wraps,
          title: el.getAttribute('title') || '',
          height: el.getBoundingClientRect().height
        };
      });
    }""")
    all_nowrap = all(x["whiteSpace"] == "nowrap" and not x["wraps"] for x in wrap_info)
    titles_ok = all(x["title"] == x["text"] for x in wrap_info)
    set_result("methods_oneline_desktop", all_nowrap and titles_ok,
               f"rows={len(wrap_info)} nowrap={all_nowrap} titles={titles_ok}")
    pg.locator("#method-list").screenshot(path=os.path.join(GALLERY, "20_methods_oneline_desktop.png"))

    # T6 Esc closes drawer + focus return
    hls = pg.query_selector_all("#tafsir [data-hid]")
    t6_ok = False
    focus_ok = False
    if hls:
        hid = hls[0].get_attribute("data-hid")
        hls[0].click()
        pg.wait_for_timeout(300)
        drawer_open = pg.is_visible("#drawer")
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(300)
        drawer_after = pg.is_visible("#drawer")
        focused = pg.evaluate("""(hid) => {
          const a = document.activeElement;
          return !!(a && a.getAttribute && a.getAttribute('data-hid') === hid);
        }""", hid)
        t6_ok = drawer_open and not drawer_after
        focus_ok = focused
        set_result("T6", t6_ok and focus_ok,
                   f"open={drawer_open} after_esc={drawer_after} focus_back={focused}")
    else:
        set_result("T6", False, "no highlights")

    # Verse collapsible + localStorage
    # ensure expanded first
    pg.evaluate("""() => { try { localStorage.removeItem('tafsir-fahras-v1-verse-collapsed'); } catch(e){} }""")
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(400)
    expanded_label = pg.inner_text("#verse-toggle-btn")
    aria_exp = pg.get_attribute("#verse-toggle-btn", "aria-expanded")
    verse_visible = pg.is_visible("#verse-text")
    font_px = pg.evaluate("""() => {
      const el = document.getElementById('verse-text');
      return parseFloat(getComputedStyle(el).fontSize);
    }""")
    pg.click("#verse-toggle-btn")
    pg.wait_for_timeout(200)
    collapsed_label = pg.inner_text("#verse-toggle-btn")
    verse_hidden = not pg.is_visible("#verse-text")
    stored = pg.evaluate("""() => {
      try { return localStorage.getItem('tafsir-fahras-v1-verse-collapsed'); } catch(e) { return null; }
    }""")
    pg.screenshot(path=os.path.join(GALLERY, "22_verse_collapsed.png"))
    # persist across reload
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(400)
    still_collapsed = pg.evaluate("document.getElementById('verse-block').classList.contains('is-collapsed')")
    verse_ok = (
        expanded_label.strip() == "إخفاء الآية"
        and aria_exp == "true"
        and verse_visible
        and 19.5 <= font_px <= 23.5
        and collapsed_label.strip() == "إظهار الآية"
        and verse_hidden
        and stored == "1"
        and still_collapsed
    )
    set_result("verse_collapsible", verse_ok,
               f"exp_lbl={expanded_label!r} font={font_px:.1f} col_lbl={collapsed_label!r} stored={stored} persist={still_collapsed}")

    # Review toolbar light
    pg.click("#start-review-btn")
    pg.wait_for_timeout(300)
    tb_visible = pg.is_visible("#review-toolbar")
    tb_label = pg.inner_text("#pen-toggle-btn")
    tools = pg.evaluate("""() => {
      const ids = ['rt-add-btn','rt-stretch-btn','rt-merge-btn','rt-restore-btn','rt-compare-btn','rt-approve-btn','rt-method-name','rt-swatch'];
      return Object.fromEntries(ids.map(id => [id, !!document.getElementById(id)]));
    }""")
    contrast = pg.evaluate("""() => {
      const bar = document.getElementById('review-toolbar');
      const label = document.getElementById('pen-toggle-btn');
      const cs = getComputedStyle(bar);
      const ls = getComputedStyle(label);
      return { bg: cs.backgroundColor, fg: ls.color, border: cs.borderTopColor };
    }""")
    bg = parse_rgb(contrast["bg"])
    fg = parse_rgb(contrast["fg"])
    # pen button is primary (violet on white text) — check bar ink via method name
    method_fg = pg.evaluate("() => getComputedStyle(document.getElementById('rt-method-name')).color")
    method_bg = pg.evaluate("() => getComputedStyle(document.getElementById('rt-method')).backgroundColor")
    mfg = parse_rgb(method_fg)
    mbg = parse_rgb(method_bg)
    ratio = contrast_ratio(mfg, mbg) if mfg and mbg else 0
    # also check pen button white-on-violet
    pen_fg = parse_rgb(pg.evaluate("() => getComputedStyle(document.getElementById('pen-toggle-btn')).color"))
    pen_bg = parse_rgb(pg.evaluate("() => getComputedStyle(document.getElementById('pen-toggle-btn')).backgroundColor"))
    pen_ratio = contrast_ratio(pen_fg, pen_bg) if pen_fg and pen_bg else 0
    best_ratio = max(ratio, pen_ratio)
    pg.screenshot(path=os.path.join(GALLERY, "23_review_toolbar_light.png"))
    tools_ok = all(tools.values())
    set_result("review_toolbar_light", tb_visible and "قلم التمييز" in tb_label and tools_ok and best_ratio >= 4.5,
               f"visible={tb_visible} label={tb_label!r} tools={tools_ok} contrast={best_ratio:.2f}")

    # T9: select + add highlight + compare + approve (via toolbar when possible)
    rect = pg.evaluate("""() => {
      var el = document.getElementById('tafsir');
      var walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      var node = walker.nextNode();
      while (node && node.textContent.trim().length < 20) node = walker.nextNode();
      if (!node) return null;
      var r = document.createRange();
      r.selectNodeContents(node);
      var rects = r.getClientRects();
      if (!rects.length) return null;
      var rc = rects[rects.length - 1];
      node.parentElement.scrollIntoView({block:'center'});
      return {x:rc.x, y:rc.y, w:rc.width, h:rc.height};
    }""")
    pg.wait_for_timeout(200)
    t9_ok = False
    if rect:
        cx = rect["x"] + rect["w"] * 0.7
        cy = rect["y"] + rect["h"] * 0.5
        pg.mouse.move(cx, cy)
        pg.mouse.down()
        pg.mouse.move(cx - 120, cy, steps=10)
        pg.mouse.up()
        pg.wait_for_timeout(300)
        if pg.is_visible("#palette-ok"):
            pg.click("#palette-ok")
            pg.wait_for_timeout(300)
    # Prefer drawer compare/approve when drawer is open (covers toolbar); else toolbar
    if pg.is_visible("#drawer") and pg.is_visible("#compare-source-btn"):
        pg.click("#compare-source-btn")
        pg.wait_for_timeout(300)
        if pg.is_enabled("#drawer-approve-btn"):
            pg.click("#drawer-approve-btn")
            pg.wait_for_timeout(300)
        approved = pg.evaluate("document.body.innerText.includes('معتمد')")
        t9_ok = bool(approved)
    elif pg.is_enabled("#rt-compare-btn"):
        pg.click("#rt-compare-btn", force=True)
        pg.wait_for_timeout(300)
        if pg.is_enabled("#rt-approve-btn"):
            pg.click("#rt-approve-btn", force=True)
            pg.wait_for_timeout(300)
        approved = pg.evaluate("document.body.innerText.includes('معتمد')")
        t9_ok = bool(approved)
    set_result("T9", t9_ok, "review→compare→approve via toolbar/drawer")

    # T11 schema validation on export-current
    if pg.is_visible("#drawer-close"):
        pg.click("#drawer-close")
        pg.wait_for_timeout(150)
    pg.click("#export-menu-btn")
    pg.wait_for_timeout(200)
    t11_ok = False
    t11_note = ""
    if pg.is_visible("#export-current-btn"):
        pg.click("#export-current-btn")
        pg.wait_for_timeout(300)
        txt = pg.input_value("#export-text")
        try:
            data = json.loads(txt)
            # ensure changes strip tafsir/annotator
            changes = (((data.get("review") or {}).get("changes")) or [])
            bad = [c for c in changes if "tafsir" in c or "annotator" in c]
            jsonschema.validate(instance=data, schema=schema)
            t11_ok = len(bad) == 0
            t11_note = f"schema_ok changes={len(changes)} stripped_ok={len(bad)==0}"
        except Exception as e:
            t11_note = str(e)[:200]
    set_result("T11", t11_ok, t11_note)

    # Side-by-side 12/12
    if pg.get_attribute("#side-by-side-btn", "aria-pressed") != "true":
        pg.click("#side-by-side-btn")
        pg.wait_for_timeout(200)
    total = 0
    passed = 0
    tafsir_n = pg.eval_on_selector("#tafsir-select", "el => el.options.length")
    for ti in range(tafsir_n):
        pg.eval_on_selector("#tafsir-select", "(el,i)=>{el.selectedIndex=i; el.dispatchEvent(new Event('change',{bubbles:true}));}", ti)
        pg.wait_for_timeout(180)
        if pg.get_attribute("#side-by-side-btn", "aria-pressed") != "true":
            pg.click("#side-by-side-btn"); pg.wait_for_timeout(150)
        verse_n = pg.eval_on_selector("#win-select", "el => el.options.length")
        for vi in range(verse_n):
            pg.eval_on_selector("#win-select", "(el,i)=>{el.selectedIndex=i; el.dispatchEvent(new Event('change',{bubbles:true}));}", vi)
            pg.wait_for_timeout(180)
            total += 1
            banner = pg.inner_text("#match-banner") if pg.is_visible("#match-banner") else ""
            if "✅" in banner and "متطابق" in banner:
                passed += 1
    set_result("side_by_side", passed == 12 and total == 12, f"{passed}/{total}")
    ctx.close()

    # ---- 375px methods + compact toolbar (fresh context) ----
    ctx375 = b.new_context(viewport={"width": 375, "height": 812}, color_scheme="light", locale="ar-SA", is_mobile=True, has_touch=True)
    pg375 = ctx375.new_page()
    pg375.goto(BASE, wait_until="networkidle")
    pg375.wait_for_timeout(500)
    wrap375 = pg375.evaluate("""() => {
      const names = Array.from(document.querySelectorAll('#method-list .method-name'));
      return names.map(el => {
        const cs = getComputedStyle(el);
        const wraps = el.scrollHeight > el.clientHeight + 2;
        return { text: el.textContent, whiteSpace: cs.whiteSpace, wraps, title: el.title };
      });
    }""")
    ok375 = all(x["whiteSpace"] == "nowrap" and not x["wraps"] for x in wrap375)
    set_result("methods_oneline_375", ok375, f"rows={len(wrap375)}")
    pg375.evaluate("document.getElementById('method-list')?.scrollIntoView({block:'start'})")
    pg375.wait_for_timeout(150)
    pg375.locator("#method-list").screenshot(path=os.path.join(GALLERY, "21_methods_oneline_375.png"))

    # review toolbar compact — must not cover tafsir text
    pg375.evaluate("window.scrollTo(0,0)")
    pg375.wait_for_timeout(100)
    pg375.click("#start-review-btn")
    pg375.wait_for_timeout(300)
    pg375.evaluate("""() => {
      const bar = document.getElementById('review-toolbar');
      const page = document.querySelector('.panel-page');
      if (page) page.scrollIntoView({block:'start'});
      if (bar) bar.scrollIntoView({block:'start'});
    }""")
    pg375.wait_for_timeout(200)
    cover = pg375.evaluate("""() => {
      const bar = document.getElementById('review-toolbar');
      const tafsir = document.getElementById('tafsir');
      if (!bar || bar.hidden || !tafsir) return {ok:false, reason:'missing'};
      const br = bar.getBoundingClientRect();
      const tr = tafsir.getBoundingClientRect();
      // Toolbar sits above tafsir in document flow; covering means overlapping the tafsir box.
      const textCovered = br.bottom > tr.top + 4 && br.top < tr.top + 20;
      return { ok: !textCovered && br.height <= 72, textCovered, barH: Math.round(br.height), barBottom: Math.round(br.bottom), tafsirTop: Math.round(tr.top) };
    }""")
    set_result("review_toolbar_375_no_cover", cover.get("ok"), str(cover))
    ctx375.close()

    # ---- Dark toolbar ----
    ctxd = b.new_context(viewport={"width": 1440, "height": 900}, color_scheme="dark", locale="ar-SA")
    pgd = ctxd.new_page()
    pgd.goto(BASE, wait_until="networkidle")
    pgd.wait_for_timeout(400)
    # force dark via site toggle if present
    theme_btn = pgd.query_selector("#theme-btn, .theme-btn, [data-theme-toggle]")
    if theme_btn:
        # click until dark
        for _ in range(2):
            cur = pgd.evaluate("document.documentElement.getAttribute('data-theme')")
            if cur == "dark":
                break
            theme_btn.click()
            pgd.wait_for_timeout(150)
    else:
        pgd.evaluate("document.documentElement.setAttribute('data-theme','dark')")
        pgd.wait_for_timeout(100)
    pgd.click("#start-review-btn")
    pgd.wait_for_timeout(300)
    dark_vis = pgd.is_visible("#review-toolbar")
    pen_fg = parse_rgb(pgd.evaluate("() => getComputedStyle(document.getElementById('pen-toggle-btn')).color"))
    pen_bg = parse_rgb(pgd.evaluate("() => getComputedStyle(document.getElementById('pen-toggle-btn')).backgroundColor"))
    mfg = parse_rgb(pgd.evaluate("() => getComputedStyle(document.getElementById('rt-method-name')).color"))
    mbg = parse_rgb(pgd.evaluate("() => getComputedStyle(document.getElementById('rt-method')).backgroundColor"))
    dark_ratio = 0
    if pen_fg and pen_bg:
        dark_ratio = max(dark_ratio, contrast_ratio(pen_fg, pen_bg))
    if mfg and mbg:
        dark_ratio = max(dark_ratio, contrast_ratio(mfg, mbg))
    pgd.screenshot(path=os.path.join(GALLERY, "24_review_toolbar_dark.png"))
    set_result("review_toolbar_dark", dark_vis and dark_ratio >= 4.5, f"visible={dark_vis} contrast={dark_ratio:.2f}")
    ctxd.close()
    b.close()

print("\n=== SUMMARY ===")
for k, (st, note) in results.items():
    print(f"{st}\t{k}\t{note}")
fail_n = sum(1 for st, _ in results.values() if st == "FAIL")
sys.exit(1 if fail_n else 0)
