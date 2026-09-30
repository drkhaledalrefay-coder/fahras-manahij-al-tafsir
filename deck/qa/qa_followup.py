import json, os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8791/fahras.html"
GALLERY = os.path.join(os.path.dirname(__file__), "gallery")
SHOTS = os.path.join(os.path.dirname(__file__), "shots")

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    ctx = b.new_context(viewport={"width":1440,"height":900}, color_scheme="light", locale="ar-SA")
    pg = ctx.new_page()
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type=="error" else None)
    pg.goto(BASE, wait_until="networkidle")
    pg.wait_for_timeout(500)

    # T5 methods panel with correct selector
    print("=== T5 ===")
    all_btn = pg.query_selector("[data-all]")
    none_btn = pg.query_selector("[data-none]")
    rows = pg.query_selector_all("#method-list .method-row")
    print("rows found:", len(rows), "data-all:", bool(all_btn), "data-none:", bool(none_btn))
    # find a row with nonzero primary count
    best_idx = None
    for i, r in enumerate(rows):
        txt = r.query_selector(".method-count").inner_text()
        if "0" not in txt.split("·")[0]:
            best_idx = i
            print("picked row", i, "count:", txt)
            break
    if best_idx is None:
        best_idx = 0
    if none_btn:
        none_btn.click(); pg.wait_for_timeout(200)
        hc_none = pg.eval_on_selector_all("#tafsir [data-hid]", "els=>els.length")
        print("after لا شيء: hc=", hc_none)
    rows2 = pg.query_selector_all("#method-list .method-row")
    cb = rows2[best_idx].query_selector("input[type=checkbox]") if rows2 else None
    if cb:
        cb.click(); pg.wait_for_timeout(200)
        hc_one = pg.eval_on_selector_all("#tafsir [data-hid]", "els=>els.length")
        print("after enabling one method only: hc=", hc_one)
        pg.screenshot(path=os.path.join(GALLERY, "02_methods_filter.png"))
    if all_btn:
        all_btn.click(); pg.wait_for_timeout(200)
        hc_all = pg.eval_on_selector_all("#tafsir [data-hid]", "els=>els.length")
        print("after الكل: hc=", hc_all)

    # T6 drawer open + Esc close (clean)
    print("=== T6 ===")
    hls = pg.query_selector_all("#tafsir [data-hid]")
    if hls:
        hls[0].click()
        pg.wait_for_timeout(300)
        drawer_open = pg.is_visible("#drawer")
        print("drawer_open:", drawer_open)
        pg.screenshot(path=os.path.join(GALLERY, "03_why_drawer.png"))
        if pg.is_visible("#flash-evidence"):
            pg.click("#flash-evidence")
            pg.wait_for_timeout(150)
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(300)
        drawer_after_esc = pg.is_visible("#drawer")
        print("drawer_visible_after_esc:", drawer_after_esc, "(expected False if Esc closes it)")
        if drawer_after_esc and pg.is_visible("#drawer-close"):
            pg.click("#drawer-close")
            pg.wait_for_timeout(200)
        # now test close via button
        hls = pg.query_selector_all("#tafsir [data-hid]")
        hls[0].click()
        pg.wait_for_timeout(300)
        if pg.is_visible("#drawer-close"):
            pg.click("#drawer-close")
            pg.wait_for_timeout(200)
        drawer_after_btn = pg.is_visible("#drawer")
        print("drawer_visible_after_close_btn:", drawer_after_btn, "(expected False)")

    # T9 review flow clean, scroll into view before interacting
    print("=== T9 ===")
    pg.click("#start-review-btn")
    pg.wait_for_timeout(300)
    review_on = pg.is_visible("#spec-tools")
    print("review_on:", review_on)
    pg.wait_for_timeout(200)
    rect = pg.evaluate("""() => {
        var el = document.getElementById('tafsir');
        var walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
        var node = walker.nextNode();
        while(node && node.textContent.trim().length < 20) node = walker.nextNode();
        if(!node) return null;
        var r = document.createRange();
        r.selectNodeContents(node);
        var rects = r.getClientRects();
        if (!rects.length) return null;
        var rc = rects[0];
        node.parentElement.scrollIntoView({block:'center'});
        return null;
    }""")
    pg.wait_for_timeout(200)
    rect = pg.evaluate("""() => {
        var el = document.getElementById('tafsir');
        var walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
        var node = walker.nextNode();
        while(node && node.textContent.trim().length < 20) node = walker.nextNode();
        if(!node) return null;
        var r = document.createRange();
        r.selectNodeContents(node);
        var rects = r.getClientRects();
        if (!rects.length) return null;
        var rc = rects[rects.length-1];
        return {x:rc.x, y:rc.y, w:rc.width, h:rc.height, text: node.textContent.slice(0,20)};
    }""")
    print("target rect:", rect)
    if rect:
        cx = rect["x"] + rect["w"]*0.7
        cy = rect["y"] + rect["h"]*0.5
        pg.mouse.move(cx, cy)
        pg.mouse.down()
        pg.mouse.move(cx - 120, cy, steps=10)
        pg.mouse.up()
        pg.wait_for_timeout(300)
        sel_text = pg.evaluate("window.getSelection().toString()")
        print("selected text via mouse drag:", repr(sel_text))
    else:
        print("no suitable text node found")
    palette_visible = pg.is_visible("#palette")
    print("palette_visible:", palette_visible)
    if palette_visible:
        box = pg.eval_on_selector("#palette", "el => { var r = el.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; }")
        print("palette box:", box)
        pg.screenshot(path=os.path.join(GALLERY, "05_review_highlighter.png"))
        ok_btn = pg.query_selector("#palette-ok")
        if ok_btn:
            ok_visible = ok_btn.is_visible()
            print("palette-ok visible:", ok_visible)
            if ok_visible:
                ok_btn.scroll_into_view_if_needed()
                ok_btn.click(force=True)
                pg.wait_for_timeout(300)
                hls2 = pg.query_selector_all("#tafsir [data-hid]")
                print("highlights after add:", len(hls2))
                drawer_already_open = pg.is_visible("#drawer")
                print("drawer_already_open_after_add:", drawer_already_open)
                if hls2 and not drawer_already_open:
                    hls2[-1].scroll_into_view_if_needed()
                    hls2[-1].click(timeout=5000)
                    pg.wait_for_timeout(300)
                if hls2:
                    if pg.is_visible("#compare-source-btn"):
                        pg.click("#compare-source-btn")
                        pg.wait_for_timeout(300)
                        badge = pg.is_visible("#compare-badge")
                        fail = pg.is_visible("#compare-fail")
                        approve_enabled = pg.is_enabled("#drawer-approve-btn") if pg.is_visible("#drawer-approve-btn") else None
                        print("compare_badge:", badge, "compare_fail:", fail, "approve_enabled:", approve_enabled)
                        pg.screenshot(path=os.path.join(GALLERY, "05_review_highlighter.png"))
                        if approve_enabled:
                            pg.click("#drawer-approve-btn")
                            pg.wait_for_timeout(300)
                            status_txt = pg.evaluate("document.body.innerText.includes('معتمد')")
                            print("status includes معتمد:", status_txt)
        # test footnote refusal: try selecting text starting with ¬ if present
        has_footnote = pg.evaluate("document.getElementById('tafsir').innerText.includes('¬')")
        print("has_footnote_marker:", has_footnote)

    # close drawer/palette to leave clean state
    pg.keyboard.press("Escape")
    if pg.is_visible("#drawer-close"):
        pg.click("#drawer-close")
    pg.wait_for_timeout(200)

    # T13 font size + persistence retry cleanly
    print("=== T13 ===")
    if pg.is_visible("#type-larger"):
        pg.click("#type-larger")
        pg.wait_for_timeout(150)
        size1 = pg.eval_on_selector("#tafsir", "el => getComputedStyle(el).fontSize")
        pg.reload(wait_until="networkidle")
        pg.wait_for_timeout(400)
        size2 = pg.eval_on_selector("#tafsir", "el => getComputedStyle(el).fontSize")
        print("size_after_click:", size1, "size_after_reload:", size2, "persisted:", size1==size2)

    # T15 collapsibles clean
    print("=== T15 ===")
    if pg.is_visible("#results-summary"):
        before = pg.get_attribute("#results-disclose", "open") is not None
        pg.click("#results-summary")
        pg.wait_for_timeout(150)
        after = pg.get_attribute("#results-disclose", "open") is not None
        print("results-disclose open:", before, "->", after)
    if pg.is_visible("#queue-summary"):
        before2 = pg.get_attribute("#spec-queue", "open") is not None
        pg.click("#queue-summary")
        pg.wait_for_timeout(150)
        after2 = pg.get_attribute("#spec-queue", "open") is not None
        print("spec-queue open:", before2, "->", after2)

    print("console_errors:", errs)
    b.close()
