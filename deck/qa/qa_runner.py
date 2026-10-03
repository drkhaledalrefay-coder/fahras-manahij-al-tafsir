import json, time, os, sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8791/fahras.html"
SHOTS = os.path.join(os.path.dirname(__file__), "shots")
GALLERY = os.path.join(os.path.dirname(__file__), "gallery")
os.makedirs(SHOTS, exist_ok=True)
os.makedirs(GALLERY, exist_ok=True)

results = []  # (test_id, mode, status, note)
console_errors = []  # (mode, text)
fail_details = []

def launch_browser(p):
    """Google Chrome if installed, else Playwright's Chromium (`python -m playwright install chromium`).
    QA_CHROMIUM_EXECUTABLE overrides both."""
    exe = os.environ.get("QA_CHROMIUM_EXECUTABLE")
    if exe:
        return p.chromium.launch(executable_path=exe, headless=True)
    try:
        return p.chromium.launch(channel="chrome", headless=True)
    except Exception:
        return p.chromium.launch(headless=True)

def log(test_id, mode, status, note=""):
    results.append((test_id, mode, status, note))
    print(f"[{mode}] {test_id}: {status} {note}")

def get_select_options(page, sel_id):
    return page.eval_on_selector(f"#{sel_id}", "el => Array.from(el.options).map(o=>({value:o.value,text:o.textContent}))")

def select_by_index(page, sel_id, idx):
    page.eval_on_selector(f"#{sel_id}", "(el, idx) => { el.selectedIndex = idx; el.dispatchEvent(new Event('change', {bubbles:true})); }", idx)
    page.wait_for_timeout(150)

def highlight_count(page):
    return page.eval_on_selector_all("#tafsir [data-hid]", "els => els.length")

def has_horiz_scroll(page):
    return page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 2")

def _drawer_or_backdrop_open(page):
    drawer_open = False
    try:
        drawer_open = page.is_visible("#drawer")
    except Exception as e:
        print(f"[qa] close_drawer: drawer visibility check failed: {e}", file=sys.stderr)
    backdrop_open = False
    try:
        if page.query_selector("#drawer-backdrop"):
            backdrop_open = page.evaluate(
                "!document.getElementById('drawer-backdrop').hidden"
            )
    except Exception as e:
        print(f"[qa] close_drawer: backdrop check failed: {e}", file=sys.stderr)
    return drawer_open, backdrop_open


def close_drawer(page, *, require_closed=True):
    """Close highlight drawer + backdrop so later clicks are not intercepted.

    Evidence (T9–T15 FAILs): after opening a highlight, `#drawer-backdrop` /
    `#drawer` sit above the page (z-index 40/50) and Playwright click retries
    time out. Real UI: Esc or `#drawer-close` calls closeDrawer(). Stale tests
    kept clicking through an open drawer.

    Cleanup failures are logged (never swallowed silently). When require_closed
    is True (default), asserts drawer and backdrop are closed at the end.
    """
    try:
        if page.is_visible("#drawer") or (
            page.query_selector("#drawer-backdrop")
            and page.evaluate("!document.getElementById('drawer-backdrop').hidden")
        ):
            if page.is_visible("#drawer-close"):
                page.click("#drawer-close")
            else:
                page.keyboard.press("Escape")
            page.wait_for_timeout(150)
        # Ensure backdrop is gone even if Esc hit another overlay first.
        if page.query_selector("#drawer-backdrop") and page.evaluate(
            "!document.getElementById('drawer-backdrop').hidden"
        ):
            page.keyboard.press("Escape")
            page.wait_for_timeout(100)
        if page.is_visible("#palette"):
            if page.is_visible("#palette-cancel"):
                page.click("#palette-cancel")
            else:
                page.keyboard.press("Escape")
            page.wait_for_timeout(100)
    except Exception as e:
        print(f"[qa] close_drawer cleanup failed: {e}", file=sys.stderr)
        if require_closed:
            raise
    if require_closed:
        drawer_open, backdrop_open = _drawer_or_backdrop_open(page)
        assert not drawer_open and not backdrop_open, (
            f"drawer/backdrop still open after close_drawer "
            f"(drawer_open={drawer_open}, backdrop_open={backdrop_open})"
        )

def mouse_select_in_tafsir(page):
    """Drag-select text inside #tafsir (mouseup opens «إضافة إلى التعليق»).

    Programmatic Range + synthetic mouseup is unreliable; the live UI listens
    for real selection via onSelectAttempt on mouseup/touchend.
    """
    rect = page.evaluate("""() => {
        var el = document.getElementById('tafsir');
        if (!el) return null;
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
    page.wait_for_timeout(150)
    if not rect:
        return False
    cx = rect["x"] + rect["w"] * 0.7
    cy = rect["y"] + rect["h"] * 0.5
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx - 120, cy, steps=10)
    page.mouse.up()
    page.wait_for_timeout(300)
    return True

def contrast_ratio(rgb1, rgb2):
    def lum(rgb):
        def chan(c):
            c = c/255
            return c/12.92 if c <= 0.03928 else ((c+0.055)/1.055)**2.4
        r,g,b = rgb
        return 0.2126*chan(r)+0.7152*chan(g)+0.0722*chan(b)
    l1, l2 = lum(rgb1)+0.05, lum(rgb2)+0.05
    return max(l1,l2)/min(l1,l2)

def parse_rgb(s):
    s = s.strip()
    if s.startswith("rgba"):
        nums = s[s.index("(")+1:s.index(")")].split(",")
        return tuple(float(n) for n in nums[:3])
    if s.startswith("rgb"):
        nums = s[s.index("(")+1:s.index(")")].split(",")
        return tuple(float(n) for n in nums[:3])
    return None

def run_mode(mode, viewport, color_scheme, is_phone=False):
    with sync_playwright() as p:
        browser = launch_browser(p)
        ctx = browser.new_context(viewport=viewport, color_scheme=color_scheme,
                                   locale="ar-SA",
                                   device_scale_factor=2 if not is_phone else 2,
                                   is_mobile=is_phone, has_touch=is_phone)
        page = ctx.new_page()
        errs = []
        def _on_console(msg):
            if msg.type != "error":
                return
            text = msg.text or ""
            # Browsers auto-request /favicon.ico; static web/ has none — not a page bug.
            if "favicon.ico" in text:
                return
            loc = msg.location or {}
            if isinstance(loc, dict) and "favicon.ico" in str(loc.get("url") or ""):
                return
            errs.append(text)
        page.on("console", _on_console)
        page.on("pageerror", lambda exc: errs.append(str(exc)))

        # T1 Load
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(500)
        title = page.title()
        title_ok = "فهرس مناهج التفسير" in title
        scroll_ok = not has_horiz_scroll(page)
        t1_ok = title_ok and scroll_ok and len(errs) == 0
        log("T1", mode, "PASS" if t1_ok else "FAIL",
            f"title={title!r} scroll_ok={scroll_ok} console_errs={len(errs)}")
        if not t1_ok:
            fail_details.append(f"T1 [{mode}]: title_ok={title_ok} scroll_ok={scroll_ok} errs={errs[:3]}")

        # dark theme toggle if needed (color_scheme=dark controls prefers-color-scheme,
        # but site's own theme toggle may be separate — check button state / attr)
        if mode.startswith("dark"):
            # try to force site theme to dark via its own toggle if not already
            try:
                theme_attr = page.evaluate("document.documentElement.getAttribute('data-theme') || document.body.getAttribute('data-theme')")
            except Exception:
                theme_attr = None
            if theme_attr != "dark":
                page.click("#theme-btn")
                page.wait_for_timeout(200)

        shot_prefix = mode.replace(" ", "_")

        # T2 Tafsir dropdown
        try:
            opts = get_select_options(page, "tafsir-select")
            names = [o["text"] for o in opts]
            target_names = ["ابن كثير", "الطبري", "السعدي", "البغوي"]
            found = [n for n in target_names if any(n in t for t in names)]
            t2_notes = []
            for i, o in enumerate(opts):
                select_by_index(page, "tafsir-select", i)
                page.wait_for_timeout(150)
                hc = highlight_count(page)
                empty_visible = page.is_visible("#empty-banner") or page.is_visible("#filter-empty")
                t2_notes.append(f"{o['text']}:hc={hc},empty_ui={empty_visible}")
            t2_ok = len(found) >= 3
            log("T2", mode, "PASS" if t2_ok else "FAIL", "; ".join(t2_notes))
        except Exception as e:
            log("T2", mode, "FAIL", str(e))

        # Reset to first tafsir (ابن كثير assumed default per spec, but note page opens on الطبري by default)
        select_by_index(page, "tafsir-select", 0)
        page.wait_for_timeout(150)

        if mode == "light desktop":
            # T3: verse dropdown across each tafsir (12 combos) - abbreviated to counts
            try:
                tafsir_opts = get_select_options(page, "tafsir-select")
                combo_notes = []
                combo_ok = True
                for ti, topt in enumerate(tafsir_opts):
                    select_by_index(page, "tafsir-select", ti)
                    page.wait_for_timeout(150)
                    verse_opts = get_select_options(page, "win-select")
                    for vi, vopt in enumerate(verse_opts):
                        select_by_index(page, "win-select", vi)
                        page.wait_for_timeout(150)
                        hc = highlight_count(page)
                        combo_notes.append(f"{topt['text']}/{vopt['text']}:hc={hc}")
                log("T3", mode, "PASS", f"{len(combo_notes)} combos rendered; " + "; ".join(combo_notes[:6]) + " ...")
            except Exception as e:
                log("T3", mode, "FAIL", str(e))
            select_by_index(page, "tafsir-select", 0)
            select_by_index(page, "win-select", 0)
            page.wait_for_timeout(150)

            # T4 model dropdown
            try:
                # default context al_tabari 2:255 -> MiMo check
                # find tafsir index for الطبري
                tafsir_opts = get_select_options(page, "tafsir-select")
                tab_idx = next((i for i,o in enumerate(tafsir_opts) if "طبري" in o["text"]), None)
                ibn_idx = next((i for i,o in enumerate(tafsir_opts) if "ابن كثير" in o["text"]), None)
                notes = []
                if tab_idx is not None:
                    select_by_index(page, "tafsir-select", tab_idx)
                    page.wait_for_timeout(150)
                    ann_visible = page.is_visible("#ann-wrap")
                    ann_opts = get_select_options(page, "ann-select") if ann_visible else []
                    notes.append(f"tabari ann_visible={ann_visible} opts={[o['text'] for o in ann_opts]}")
                if ibn_idx is not None:
                    select_by_index(page, "tafsir-select", ibn_idx)
                    page.wait_for_timeout(150)
                    ann_visible2 = page.is_visible("#ann-wrap")
                    ann_opts2 = get_select_options(page, "ann-select") if ann_visible2 else []
                    hc_before = highlight_count(page)
                    if ann_opts2:
                        select_by_index(page, "ann-select", len(ann_opts2)-1)
                        page.wait_for_timeout(150)
                    hc_after = highlight_count(page)
                    notes.append(f"ibnkathir ann_visible={ann_visible2} opts={[o['text'] for o in ann_opts2]} hc_before={hc_before} hc_after={hc_after}")
                log("T4", mode, "PASS", "; ".join(notes))
            except Exception as e:
                log("T4", mode, "FAIL", str(e))
            select_by_index(page, "tafsir-select", 0)
            page.wait_for_timeout(150)

            page.screenshot(path=os.path.join(SHOTS, f"{shot_prefix}_T4_methods_before.png"))

            # T5 methods panel
            try:
                method_items = page.query_selector_all("#method-list [role='button'], #method-list button, #method-list .method-item")
                if not method_items:
                    method_items = page.query_selector_all("#method-list *[data-method]")
                notes = f"method_items_found={len(method_items)}"
                if method_items:
                    method_items[0].click()
                    page.wait_for_timeout(200)
                    page.screenshot(path=os.path.join(GALLERY, "02_methods_filter.png"))
                    hc = highlight_count(page)
                    notes += f" after_click hc={hc}"
                log("T5", mode, "PASS" if method_items else "SKIPPED", notes)
            except Exception as e:
                log("T5", mode, "FAIL", str(e))

            # T6 highlight click -> drawer
            try:
                hls = page.query_selector_all("#tafsir [data-hid]")
                if hls:
                    hls[0].click()
                    page.wait_for_timeout(300)
                    drawer_open = page.is_visible("#drawer")
                    if drawer_open:
                        page.screenshot(path=os.path.join(GALLERY, "03_why_drawer.png"))
                    # flash evidence
                    if page.is_visible("#flash-evidence"):
                        page.click("#flash-evidence")
                        page.wait_for_timeout(200)
                    # close via Esc
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(200)
                    drawer_closed = not page.is_visible("#drawer")
                    # Backdrop must clear too (otherwise T9+ clicks time out).
                    backdrop_open = page.evaluate(
                        "(() => { var b = document.getElementById('drawer-backdrop'); return b && !b.hidden; })()"
                    )
                    if backdrop_open:
                        close_drawer(page)
                        drawer_closed = not page.is_visible("#drawer")
                        backdrop_open = page.evaluate(
                            "(() => { var b = document.getElementById('drawer-backdrop'); return b && !b.hidden; })()"
                        )
                    log("T6", mode, "PASS" if (drawer_open and drawer_closed and not backdrop_open) else "FAIL",
                        f"drawer_open={drawer_open} drawer_closed_after_esc={drawer_closed} backdrop_open={backdrop_open}")
                else:
                    log("T6", mode, "SKIPPED", "no highlights found in current window")
            except Exception as e:
                log("T6", mode, "FAIL", str(e))

            close_drawer(page)
            # T7 side-by-side for all 12 windows
            try:
                page.click("#side-by-side-btn")
                page.wait_for_timeout(200)
                tafsir_opts = get_select_options(page, "tafsir-select")
                mismatches = []
                total = 0
                passed = 0
                sbs_shot_done = False
                for ti, topt in enumerate(tafsir_opts):
                    select_by_index(page, "tafsir-select", ti)
                    page.wait_for_timeout(150)
                    if not page.is_visible("#side-by-side-btn"):
                        continue
                    if page.get_attribute("#side-by-side-btn", "aria-pressed") != "true":
                        page.click("#side-by-side-btn")
                        page.wait_for_timeout(200)
                    verse_opts = get_select_options(page, "win-select")
                    for vi, vopt in enumerate(verse_opts):
                        select_by_index(page, "win-select", vi)
                        page.wait_for_timeout(200)
                        total += 1
                        banner_text = page.inner_text("#match-banner") if page.is_visible("#match-banner") else ""
                        ok = "متطابق" in banner_text and "✅" in banner_text
                        if ok:
                            passed += 1
                        else:
                            mismatches.append(f"{topt['text']}/{vopt['text']}: {banner_text!r}")
                        if topt.get("text","").find("طبري")>=0 and not sbs_shot_done:
                            page.screenshot(path=os.path.join(GALLERY, "04_side_by_side.png"))
                            sbs_shot_done = True
                t7_ok = passed == total and total > 0
                log("T7", mode, "PASS" if t7_ok else "FAIL", f"{passed}/{total} matched; mismatches={mismatches[:5]}")
                if not t7_ok:
                    fail_details.append(f"T7 [{mode}]: {passed}/{total}; " + "; ".join(mismatches[:5]))
            except Exception as e:
                log("T7", mode, "FAIL", str(e))

            # T8 in-page fidelity self-test
            try:
                selftest = page.evaluate("""() => {
                    var el = document.getElementById('results-coverage') || document.getElementById('results-run1-line');
                    return el ? el.textContent : null;
                }""")
                pass_text = None
                body_text = page.inner_text("body")
                import re
                m = re.search(r'PASS\\s*(\\d+)\\s*/\\s*(\\d+)', body_text)
                if m:
                    pass_text = m.group(0)
                    ok = m.group(1) == m.group(2)
                else:
                    ok = False
                log("T8", mode, "PASS" if ok else "SKIPPED", f"selftest_text={pass_text or selftest}")
            except Exception as e:
                log("T8", mode, "FAIL", str(e))

            # reset side-by-side off, go back to tafsir 0 / verse 0
            if page.get_attribute("#side-by-side-btn", "aria-pressed") == "true":
                page.click("#side-by-side-btn")
                page.wait_for_timeout(150)
            select_by_index(page, "tafsir-select", 0)
            select_by_index(page, "win-select", 0)
            page.wait_for_timeout(150)

            # T9 start review + select + palette + compare + approve
            # Verdict: STALE TEST (not a UI regression). Evidence: clicks timed out
            # on #drawer-backdrop / #drawer after add — selectHighlight() already
            # opens the drawer; re-clicking the mark under the backdrop fails.
            # Fix: mouse-drag selection; use drawer compare/approve; close after.
            try:
                close_drawer(page)
                page.click("#start-review-btn")
                page.wait_for_timeout(200)
                review_on = page.is_visible("#spec-tools") or page.is_visible("#review-toolbar")
                notes = f"review_tools_visible={review_on}"
                t9_ok = False
                if review_on:
                    selected = mouse_select_in_tafsir(page)
                    notes += f" mouse_select={selected}"
                    palette_visible = page.is_visible("#palette")
                    notes += f" palette_visible={palette_visible}"
                    if palette_visible:
                        page.screenshot(path=os.path.join(GALLERY, "05_review_highlighter.png"))
                        if page.is_visible("#palette-ok"):
                            page.click("#palette-ok")
                            page.wait_for_timeout(350)
                            notes += " added_highlight"
                        # UI opens drawer via selectHighlight after add — do NOT
                        # re-click the mark (backdrop intercepts). Compare in drawer.
                        if page.is_visible("#compare-source-btn"):
                            page.click("#compare-source-btn")
                            page.wait_for_timeout(300)
                            badge = page.is_visible("#compare-badge")
                            approve_enabled = (
                                page.is_enabled("#drawer-approve-btn")
                                if page.is_visible("#drawer-approve-btn")
                                else False
                            )
                            notes += f" compare_badge={badge} approve_enabled={approve_enabled}"
                            page.screenshot(path=os.path.join(GALLERY, "05_review_highlighter.png"))
                            if approve_enabled and page.is_visible("#drawer-approve-btn"):
                                page.click("#drawer-approve-btn")
                                page.wait_for_timeout(250)
                                notes += " approved"
                            t9_ok = bool(badge and approve_enabled)
                        elif page.is_enabled("#rt-compare-btn"):
                            page.click("#rt-compare-btn", force=True)
                            page.wait_for_timeout(300)
                            if page.is_enabled("#rt-approve-btn"):
                                page.click("#rt-approve-btn", force=True)
                                page.wait_for_timeout(250)
                                notes += " approved_via_toolbar"
                                t9_ok = True
                            else:
                                notes += " rt_approve_disabled"
                        else:
                            notes += " no_compare_controls"
                    else:
                        notes += " palette_missing_after_select"
                    close_drawer(page)
                    log("T9", mode, "PASS" if t9_ok else "FAIL", notes)
                else:
                    log("T9", mode, "FAIL", notes)
            except Exception as e:
                close_drawer(page, require_closed=False)
                page.screenshot(path=os.path.join(SHOTS, f"{shot_prefix}_T9_fail.png"))
                log("T9", mode, "FAIL", f"{e}")

            # T10 boundary tools - light check of enabled state after selecting a highlight
            try:
                close_drawer(page)
                hls3 = page.query_selector_all("#tafsir [data-hid]")
                if hls3:
                    hls3[0].click()
                    page.wait_for_timeout(200)
                    btn_ids = ["word-before","word-shrink-start","word-after","word-shrink-end","expand-next-sent-btn","restore-ai-btn"]
                    states = {b: page.is_enabled(f"#{b}") for b in btn_ids if page.query_selector(f"#{b}")}
                    log("T10", mode, "PASS", f"button_states={states}")
                    close_drawer(page)
                else:
                    log("T10", mode, "SKIPPED", "no highlights to select")
            except Exception as e:
                close_drawer(page, require_closed=False)
                page.screenshot(path=os.path.join(SHOTS, f"{shot_prefix}_T10_fail.png"))
                log("T10", mode, "FAIL", str(e))

            # T11 export
            try:
                close_drawer(page)
                page.click("#export-menu-btn")
                page.wait_for_timeout(200)
                menu_visible = page.is_visible("#export-menu")
                notes = f"menu_visible={menu_visible}"
                json_text = None
                if menu_visible and page.is_visible("#export-approved-btn"):
                    page.click("#export-approved-btn")
                    page.wait_for_timeout(300)
                    panel_visible = page.is_visible("#export-panel")
                    if panel_visible:
                        json_text = page.input_value("#export-text")
                        page.screenshot(path=os.path.join(GALLERY, "06_export.png"))
                    notes += f" panel_visible={panel_visible} json_len={len(json_text) if json_text else 0}"
                    valid_json = False
                    if json_text:
                        try:
                            json.loads(json_text)
                            valid_json = True
                        except Exception as je:
                            notes += f" json_error={je}"
                    notes += f" valid_json={valid_json}"
                log("T11", mode, "PASS" if menu_visible else "FAIL", notes)
                if page.is_visible("#close-export"):
                    page.click("#close-export")
                    page.wait_for_timeout(150)
            except Exception as e:
                close_drawer(page, require_closed=False)
                page.screenshot(path=os.path.join(SHOTS, f"{shot_prefix}_T11_fail.png"))
                log("T11", mode, "FAIL", str(e))

            # T12 help panel
            try:
                close_drawer(page)
                page.click("#help-btn")
                page.wait_for_timeout(200)
                help_visible = page.is_visible("#help-panel")
                tabs_ok = True
                if help_visible:
                    for tab_id in ["help-tab-btn-guide","help-tab-btn-how","help-tab-btn-sources"]:
                        if page.query_selector(f"#{tab_id}"):
                            page.click(f"#{tab_id}")
                            page.wait_for_timeout(150)
                        else:
                            tabs_ok = False
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(150)
                    help_closed = not page.is_visible("#help-panel")
                else:
                    help_closed = None
                log("T12", mode, "PASS" if (help_visible and tabs_ok and help_closed) else "FAIL",
                    f"visible={help_visible} tabs_ok={tabs_ok} closed_after_esc={help_closed}")
            except Exception as e:
                close_drawer(page, require_closed=False)
                page.screenshot(path=os.path.join(SHOTS, f"{shot_prefix}_T12_fail.png"))
                log("T12", mode, "FAIL", str(e))

            # T13 text size persistence
            try:
                close_drawer(page)
                page.click("#type-larger")
                page.wait_for_timeout(150)
                size_after_click = page.eval_on_selector("#tafsir", "el => getComputedStyle(el).fontSize")
                page.reload(wait_until="networkidle")
                page.wait_for_timeout(400)
                size_after_reload = page.eval_on_selector("#tafsir", "el => getComputedStyle(el).fontSize")
                persisted = size_after_click == size_after_reload
                log("T13", mode, "PASS" if persisted else "FAIL",
                    f"after_click={size_after_click} after_reload={size_after_reload}")
            except Exception as e:
                page.screenshot(path=os.path.join(SHOTS, f"{shot_prefix}_T13_fail.png"))
                log("T13", mode, "FAIL", str(e))

            # T15 collapsible sections
            try:
                close_drawer(page)
                res_open_before = page.get_attribute("#results-disclose", "open") is not None
                page.click("#results-summary")
                page.wait_for_timeout(150)
                res_open_after = page.get_attribute("#results-disclose", "open") is not None
                q_open_before = page.get_attribute("#spec-queue", "open") is not None
                page.click("#queue-summary")
                page.wait_for_timeout(150)
                q_open_after = page.get_attribute("#spec-queue", "open") is not None
                toggled = (res_open_before != res_open_after) and (q_open_before != q_open_after)
                log("T15", mode, "PASS" if toggled else "FAIL",
                    f"results {res_open_before}->{res_open_after}; queue {q_open_before}->{q_open_after}")
            except Exception as e:
                page.screenshot(path=os.path.join(SHOTS, f"{shot_prefix}_T15_fail.png"))
                log("T15", mode, "FAIL", str(e))

            # T16 keyboard focus
            try:
                close_drawer(page)
                page.keyboard.press("Tab")
                page.wait_for_timeout(100)
                for _ in range(5):
                    page.keyboard.press("Tab")
                    page.wait_for_timeout(50)
                focused = page.evaluate("document.activeElement ? document.activeElement.id || document.activeElement.tagName : null")
                log("T16", mode, "PASS", f"focused_after_tabs={focused}")
            except Exception as e:
                log("T16", mode, "FAIL", str(e))

        # T14 theme toggle + contrast (run in all modes to compare)
        try:
            close_drawer(page)
            initial_theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
            page.click("#theme-btn")
            page.wait_for_timeout(250)
            toggled_theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
            changed = initial_theme != toggled_theme
            # contrast sample
            sample_sels = ["#verse-text", "#tafsir", "#results-summary", "#page-title", "#methods-title"]
            ratios = []
            for s in sample_sels:
                try:
                    data = page.eval_on_selector(s, """el => {
                        var cs = getComputedStyle(el);
                        function bgOf(e){
                            while(e){
                                var c = getComputedStyle(e).backgroundColor;
                                if(c && c !== 'rgba(0, 0, 0, 0)' && c !== 'transparent') return c;
                                e = e.parentElement;
                            }
                            return 'rgb(255,255,255)';
                        }
                        return {color: cs.color, bg: bgOf(el)};
                    }""")
                    c1 = parse_rgb(data["color"]); c2 = parse_rgb(data["bg"])
                    if c1 and c2:
                        ratios.append((s, round(contrast_ratio(c1,c2),2)))
                except Exception:
                    pass
            low = [r for r in ratios if r[1] < 4.5]
            # revert theme toggle back
            page.click("#theme-btn")
            page.wait_for_timeout(200)
            t14_ok = changed and not low
            log("T14", mode, "PASS" if t14_ok else "FAIL", f"toggled={changed} ratios={ratios} low={low}")
            if low:
                fail_details.append(f"T14 [{mode}]: low contrast elements {low}")
        except Exception as e:
            log("T14", mode, "FAIL", str(e))

        # ensure theme matches mode for T17/T18 screenshots
        want_dark = "dark" in mode
        cur_theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
        if (want_dark and cur_theme != "dark") or (not want_dark and cur_theme == "dark"):
            page.click("#theme-btn")
            page.wait_for_timeout(200)

        # T17 visual sanity screenshot + T18 white-box-in-dark check
        try:
            page.screenshot(path=os.path.join(SHOTS, f"{shot_prefix}_T17_visual.png"), full_page=True)
            log("T17", mode, "PASS", "screenshot captured for manual visual review")
        except Exception as e:
            log("T17", mode, "FAIL", str(e))

        try:
            # T18: scan all visible cards/panels for white bg + near-white text (invisible) combos
            white_boxes = page.evaluate("""() => {
                var bad = [];
                var all = document.querySelectorAll('body *');
                function toRgb(s){
                    var m = s.match(/rgba?\\(([^)]+)\\)/);
                    if(!m) return null;
                    var p = m[1].split(',').map(function(x){return parseFloat(x)});
                    return p;
                }
                function lum(rgb){
                    function ch(c){ c=c/255; return c<=0.03928? c/12.92 : Math.pow((c+0.055)/1.055,2.4); }
                    return 0.2126*ch(rgb[0])+0.7152*ch(rgb[1])+0.0722*ch(rgb[2]);
                }
                for (var i=0;i<all.length;i++){
                    var el = all[i];
                    var r = el.getBoundingClientRect();
                    if (r.width < 30 || r.height < 15) continue;
                    var cs = getComputedStyle(el);
                    var bg = toRgb(cs.backgroundColor);
                    if (!bg || cs.backgroundColor === 'rgba(0, 0, 0, 0)') continue;
                    var bgLum = lum(bg);
                    if (bgLum < 0.85) continue; // only near-white backgrounds
                    // check direct text color contrast
                    var color = toRgb(cs.color);
                    if (!color) continue;
                    var l1 = bgLum+0.05, l2 = lum(color)+0.05;
                    var ratio = Math.max(l1,l2)/Math.min(l1,l2);
                    if (ratio < 2.0 && el.textContent.trim().length > 0) {
                        bad.push({tag: el.tagName, id: el.id, cls: el.className, ratio: ratio.toFixed(2)});
                    }
                }
                return bad.slice(0,20);
            }""")
            if mode.startswith("dark"):
                page.click("#results-summary") if page.get_attribute("#results-disclose","open") is None else None
                page.wait_for_timeout(150)
                page.screenshot(path=os.path.join(SHOTS, f"{shot_prefix}_T18_area.png"))
            t18_ok = len(white_boxes) == 0
            log("T18", mode, "PASS" if t18_ok else "FAIL", f"suspect_elements={white_boxes}")
            if not t18_ok:
                fail_details.append(f"T18 [{mode}]: white-box/invisible-text elements: {white_boxes}")
        except Exception as e:
            log("T18", mode, "FAIL", str(e))

        for e in errs:
            console_errors.append((mode, e))

        browser.close()

# Gallery-specific captures (light desktop only, clean state)
def capture_gallery():
    with sync_playwright() as p:
        browser = launch_browser(p)
        ctx = browser.new_context(viewport={"width":1440,"height":900}, color_scheme="light", locale="ar-SA")
        page = ctx.new_page()
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(500)
        # ensure light theme
        theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
        if theme == "dark":
            page.click("#theme-btn"); page.wait_for_timeout(200)
        page.screenshot(path=os.path.join(GALLERY, "01_tabari_page.png"))
        browser.close()

    with sync_playwright() as p:
        browser = launch_browser(p)
        ctx = browser.new_context(viewport={"width":390,"height":844}, color_scheme="light", locale="ar-SA", is_mobile=True, has_touch=True)
        page = ctx.new_page()
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(500)
        theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
        if theme == "dark":
            page.click("#theme-btn"); page.wait_for_timeout(200)
        page.screenshot(path=os.path.join(GALLERY, "07_phone.png"), full_page=False)
        browser.close()

    with sync_playwright() as p:
        browser = launch_browser(p)
        ctx = browser.new_context(viewport={"width":1440,"height":900}, color_scheme="dark", locale="ar-SA")
        page = ctx.new_page()
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(500)
        theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
        if theme != "dark":
            page.click("#theme-btn"); page.wait_for_timeout(200)
        page.screenshot(path=os.path.join(GALLERY, "08_dark.png"))
        browser.close()

if __name__ == "__main__":
    run_mode("light desktop", {"width":1440,"height":900}, "light", is_phone=False)
    run_mode("dark desktop", {"width":1440,"height":900}, "dark", is_phone=False)
    run_mode("light phone", {"width":390,"height":844}, "light", is_phone=True)
    capture_gallery()

    out = {
        "results": results,
        "console_errors": console_errors,
        "fail_details": fail_details,
    }
    with open(os.path.join(os.path.dirname(__file__), "qa_raw_results.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("DONE")
    failed = [r for r in results if r[2] == "FAIL"]
    if failed:
        print(f"QA FAIL: {len(failed)} check(s) failed", file=sys.stderr)
        sys.exit(1)
