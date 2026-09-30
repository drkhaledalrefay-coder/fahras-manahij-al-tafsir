import json, os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright
import jsonschema

BASE = "http://localhost:8791/fahras.html"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
schema = json.load(open(os.path.join(ROOT, "schema", "annotation.schema.json"), encoding="utf-8"))

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    ctx = b.new_context(viewport={"width":1440,"height":900}, color_scheme="light", locale="ar-SA")
    pg = ctx.new_page()
    pg.goto(BASE, wait_until="networkidle")
    pg.wait_for_timeout(500)
    pg.click("#start-review-btn")
    pg.wait_for_timeout(300)

    rect = pg.evaluate("""() => {
        var el = document.getElementById('tafsir');
        var walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
        var node = walker.nextNode();
        while(node && node.textContent.trim().length < 20) node = walker.nextNode();
        if(!node) return null;
        var r = document.createRange();
        r.selectNodeContents(node);
        var rects = r.getClientRects();
        var rc = rects[rects.length-1];
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
        var rc = rects[rects.length-1];
        return {x:rc.x, y:rc.y, w:rc.width, h:rc.height};
    }""")
    cx = rect["x"] + rect["w"]*0.7
    cy = rect["y"] + rect["h"]*0.5
    pg.mouse.move(cx, cy)
    pg.mouse.down()
    pg.mouse.move(cx - 120, cy, steps=10)
    pg.mouse.up()
    pg.wait_for_timeout(300)
    if pg.is_visible("#palette-ok"):
        pg.click("#palette-ok")
        pg.wait_for_timeout(300)
    if pg.is_visible("#drawer") and pg.is_visible("#compare-source-btn"):
        pg.click("#compare-source-btn")
        pg.wait_for_timeout(300)
        if pg.is_enabled("#drawer-approve-btn"):
            pg.click("#drawer-approve-btn")
            pg.wait_for_timeout(300)
            approved_text = pg.evaluate("document.body.innerText.includes('معتمد')")
            print("approved:", approved_text)
        if pg.is_visible("#drawer-close"):
            pg.click("#drawer-close")
            pg.wait_for_timeout(200)
        # export current
        pg.click("#export-menu-btn")
        pg.wait_for_timeout(200)
        if pg.is_visible("#export-current-btn"):
            pg.click("#export-current-btn")
            pg.wait_for_timeout(300)
            txt = pg.input_value("#export-text")
            print("export-current JSON FULL:")
            print(txt)
            try:
                data = json.loads(txt)
                jsonschema.validate(instance=data, schema=schema)
                print("SCHEMA VALID: current export")
                # check text equals raw source slice via orig comparison already done by compare-source
            except jsonschema.ValidationError as e:
                print("SCHEMA INVALID:", e.message)
            except Exception as e:
                print("ERROR:", e)
    b.close()
