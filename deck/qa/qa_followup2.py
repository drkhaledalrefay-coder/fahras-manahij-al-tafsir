import json, os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright
import jsonschema

BASE = "http://localhost:8791/fahras.html"
GALLERY = os.path.join(os.path.dirname(__file__), "gallery")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
schema = json.load(open(os.path.join(ROOT, "schema", "annotation.schema.json"), encoding="utf-8"))

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light", locale="ar-SA")
    pg = ctx.new_page()
    pg.goto(BASE, wait_until="networkidle")
    pg.wait_for_timeout(500)

    print("=== T8 ===")
    fs = pg.evaluate("document.documentElement.getAttribute('data-fidelity-selftest')")
    n = pg.evaluate("document.documentElement.getAttribute('data-fidelity-n')")
    print("data-fidelity-selftest:", fs, "n:", n)

    print("=== T6 ===")
    hls = pg.query_selector_all("#tafsir [data-hid]")
    if hls:
        hid = hls[0].get_attribute("data-hid")
        hls[0].click()
        pg.wait_for_timeout(250)
        print("drawer_open:", pg.is_visible("#drawer"))
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(250)
        print("drawer_visible_after_esc:", pg.is_visible("#drawer"))
        focused = pg.evaluate(
            "(hid) => document.activeElement && document.activeElement.getAttribute('data-hid') === hid",
            hid,
        )
        print("focus_returned_to_highlight:", focused)
    else:
        print("no highlights")

    # T9 + T11 early (same approach as qa_schema_check) before heavy T7 navigation
    print("=== T9+T11 ===")
    pg.click("#start-review-btn")
    pg.wait_for_timeout(300)
    print("review_toolbar_visible:", pg.is_visible("#review-toolbar"))
    print("pen_label:", pg.inner_text("#pen-toggle-btn") if pg.is_visible("#pen-toggle-btn") else None)

    pg.evaluate("""() => {
        var el = document.getElementById('tafsir');
        var walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
        var node = walker.nextNode();
        while (node && node.textContent.trim().length < 20) node = walker.nextNode();
        if (node && node.parentElement) node.parentElement.scrollIntoView({block:'center'});
    }""")
    pg.wait_for_timeout(200)
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
        return {x:rc.x, y:rc.y, w:rc.width, h:rc.height};
    }""")
    print("target_rect:", rect)
    if rect:
        cx = rect["x"] + rect["w"] * 0.7
        cy = rect["y"] + rect["h"] * 0.5
        pg.mouse.move(cx, cy)
        pg.mouse.down()
        pg.mouse.move(cx - 120, cy, steps=10)
        pg.mouse.up()
        pg.wait_for_timeout(300)
    print("palette_visible:", pg.is_visible("#palette"))
    if pg.is_visible("#palette-ok"):
        pg.click("#palette-ok")
        pg.wait_for_timeout(300)
    if pg.is_visible("#drawer") and pg.is_visible("#compare-source-btn"):
        pg.click("#compare-source-btn")
        pg.wait_for_timeout(300)
        if pg.is_enabled("#drawer-approve-btn"):
            pg.click("#drawer-approve-btn")
            pg.wait_for_timeout(300)
            print("T9 approved:", pg.evaluate("document.body.innerText.includes('معتمد')"))
        if pg.is_visible("#drawer-close"):
            pg.click("#drawer-close")
            pg.wait_for_timeout(200)

    print("=== T11 ===")
    pg.click("#export-menu-btn")
    pg.wait_for_timeout(200)
    print("menu_visible:", pg.is_visible("#export-menu"))
    if pg.is_visible("#export-current-btn"):
        pg.click("#export-current-btn")
        pg.wait_for_timeout(300)
        print("panel_visible:", pg.is_visible("#export-panel"))
        if pg.is_visible("#export-panel"):
            txt = pg.input_value("#export-text")
            print("json_len:", len(txt))
            try:
                data = json.loads(txt)
                changes = (((data.get("review") or {}).get("changes")) or [])
                bad = [c for c in changes if "tafsir" in c or "annotator" in c]
                jsonschema.validate(instance=data, schema=schema)
                print("SCHEMA VALID: current export; changes=", len(changes), "no_tafsir_annotator=", len(bad) == 0)
            except Exception as e:
                print("SCHEMA INVALID:", e)
            pg.screenshot(path=os.path.join(GALLERY, "06_export.png"))

    # End review before T7
    if pg.get_attribute("#start-review-btn", "aria-pressed") == "true":
        pg.click("#start-review-btn")
        pg.wait_for_timeout(200)

    print("=== T7 ===")
    def opts(sel):
        return pg.eval_on_selector(f"#{sel}", "el => Array.from(el.options).map(o=>o.textContent)")
    if pg.get_attribute("#side-by-side-btn", "aria-pressed") != "true":
        pg.click("#side-by-side-btn")
        pg.wait_for_timeout(200)
    tafsir_opts = opts("tafsir-select")
    total = 0
    passed = 0
    mismatches = []
    shot_done = False
    for ti, tname in enumerate(tafsir_opts):
        pg.eval_on_selector(
            "#tafsir-select",
            "(el,i)=>{el.selectedIndex=i; el.dispatchEvent(new Event('change',{bubbles:true}));}",
            ti,
        )
        pg.wait_for_timeout(180)
        if pg.get_attribute("#side-by-side-btn", "aria-pressed") != "true":
            pg.click("#side-by-side-btn")
            pg.wait_for_timeout(150)
        verse_opts = opts("win-select")
        for vi, vname in enumerate(verse_opts):
            pg.eval_on_selector(
                "#win-select",
                "(el,i)=>{el.selectedIndex=i; el.dispatchEvent(new Event('change',{bubbles:true}));}",
                vi,
            )
            pg.wait_for_timeout(180)
            total += 1
            banner = pg.inner_text("#match-banner") if pg.is_visible("#match-banner") else ""
            ok = "✅" in banner and "متطابق" in banner
            if ok:
                passed += 1
            else:
                mismatches.append(f"{tname}/{vname}: {banner!r}")
            if "طبري" in tname and not shot_done:
                pg.screenshot(path=os.path.join(GALLERY, "04_side_by_side.png"))
                shot_done = True
    print(f"T7 result: {passed}/{total} passed")
    if mismatches:
        print("mismatches:", mismatches)
    b.close()
