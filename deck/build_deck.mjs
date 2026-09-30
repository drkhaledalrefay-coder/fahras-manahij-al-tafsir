#!/usr/bin/env node
/**
 * Capture demo screenshots + print deck.pdf via Chrome DevTools Protocol.
 * No npm deps — uses Node built-in fetch + WebSocket.
 */
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, statSync, writeFileSync, unlinkSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { setTimeout as delay } from "node:timers/promises";
import { tmpdir } from "node:os";
import { randomBytes } from "node:crypto";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const DECK = __dirname;
const SHOTS = join(DECK, "shots");
const APP = join(ROOT, "web", "app.html");
const DECK_HTML = join(DECK, "deck.html");
const DECK_PDF = join(DECK, "deck.pdf");
const PORT = 9333 + Math.floor(Math.random() * 200);
const VIEWPORT = { width: 1440, height: 900, deviceScaleFactor: 1.5 };

const CHROME_CANDIDATES = [
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  join(process.env.LOCALAPPDATA || "", "Google\\Chrome\\Application\\chrome.exe"),
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
];

function findChrome() {
  for (const p of CHROME_CANDIDATES) {
    if (p && existsSync(p)) return p;
  }
  throw new Error("Chrome/Edge not found");
}

class Cdp {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.ws = null;
    this.id = 0;
    this.pending = new Map();
    this.events = new Map();
  }

  async connect() {
    this.ws = new WebSocket(this.wsUrl);
    await new Promise((resolve, reject) => {
      this.ws.addEventListener("open", resolve, { once: true });
      this.ws.addEventListener("error", reject, { once: true });
    });
    this.ws.addEventListener("message", (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.id != null && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.error) reject(new Error(JSON.stringify(msg.error)));
        else resolve(msg.result);
        return;
      }
      if (msg.method) {
        const list = this.events.get(msg.method) || [];
        for (const fn of list) fn(msg.params);
      }
    });
  }

  on(method, fn) {
    if (!this.events.has(method)) this.events.set(method, []);
    this.events.get(method).push(fn);
  }

  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  close() {
    try { this.ws?.close(); } catch {}
  }
}

async function waitForJson(url, tries = 40) {
  for (let i = 0; i < tries; i++) {
    try {
      const res = await fetch(url);
      if (res.ok) return await res.json();
    } catch {}
    await delay(250);
  }
  throw new Error("DevTools endpoint not ready: " + url);
}

/** Connect to a page target (not the browser-level socket). */
async function connectPage(port) {
  await waitForJson(`http://127.0.0.1:${port}/json/version`);
  let targets = await waitForJson(`http://127.0.0.1:${port}/json/list`);
  let page = (targets || []).find((t) => t.type === "page" && t.webSocketDebuggerUrl);
  if (!page) {
    // Create a blank page via browser socket, then re-list
    const ver = await waitForJson(`http://127.0.0.1:${port}/json/version`);
    const browser = new Cdp(ver.webSocketDebuggerUrl);
    await browser.connect();
    await browser.send("Target.createTarget", { url: "about:blank" });
    browser.close();
    await delay(300);
    targets = await waitForJson(`http://127.0.0.1:${port}/json/list`);
    page = (targets || []).find((t) => t.type === "page" && t.webSocketDebuggerUrl);
  }
  if (!page) throw new Error("No page target available");
  const cdp = new Cdp(page.webSocketDebuggerUrl);
  await cdp.connect();
  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");
  return cdp;
}

async function evaluate(cdp, expression) {
  const r = await cdp.send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (r.exceptionDetails) {
    throw new Error("Eval failed: " + JSON.stringify(r.exceptionDetails));
  }
  return r.result?.value;
}

async function waitReady(cdp) {
  for (let i = 0; i < 40; i++) {
    const ok = await evaluate(cdp, `!!(document.getElementById('cards') && document.getElementById('cards').children.length)`);
    if (ok) return;
    await delay(250);
  }
  throw new Error("App did not finish rendering cards");
}

async function setViewport(cdp) {
  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width: VIEWPORT.width,
    height: VIEWPORT.height,
    deviceScaleFactor: VIEWPORT.deviceScaleFactor,
    mobile: false,
  });
}

async function captureClip(cdp, outPath, clip) {
  // CDP clip + deviceScaleFactor>1 yields blank images on this Chrome build.
  // Capture the full viewport, then crop with Pillow using CSS-px * DPR.
  const { data } = await cdp.send("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
  });
  const fullBuf = Buffer.from(data, "base64");
  if (!clip) {
    writeFileSync(outPath, fullBuf);
    return outPath;
  }
  const tmp = join(tmpdir(), `deck-shot-${randomBytes(6).toString("hex")}.png`);
  writeFileSync(tmp, fullBuf);
  const dpr = VIEWPORT.deviceScaleFactor;
  const left = Math.max(0, Math.floor(clip.x * dpr));
  const top = Math.max(0, Math.floor(clip.y * dpr));
  const width = Math.max(1, Math.floor(clip.width * dpr));
  const height = Math.max(1, Math.floor(clip.height * dpr));
  const r = spawnSync(
    "python",
    [
      "-c",
      "import sys; from PIL import Image; src,dst,L,T,W,H=sys.argv[1:7]; L,T,W,H=map(int,(L,T,W,H)); im=Image.open(src); w,h=im.size; L=min(L,w-1); T=min(T,h-1); im.crop((L,T,min(L+W,w),min(T+H,h))).save(dst)",
      tmp,
      outPath,
      String(left),
      String(top),
      String(width),
      String(height),
    ],
    { encoding: "utf8" },
  );
  try { unlinkSync(tmp); } catch {}
  if (r.status !== 0) {
    writeFileSync(outPath, fullBuf);
    console.warn("crop failed, kept full viewport:", r.stderr || r.stdout);
  }
  return outPath;
}

async function boundingBox(cdp, selector) {
  return evaluate(cdp, `(() => {
    const el = document.querySelector(${JSON.stringify(selector)});
    if (!el) return null;
    el.scrollIntoView({ block: "center", inline: "nearest", behavior: "auto" });
    const r = el.getBoundingClientRect();
    const pad = 12;
    return {
      x: Math.max(0, r.left - pad),
      y: Math.max(0, r.top - pad),
      width: Math.min(window.innerWidth - Math.max(0, r.left - pad), r.width + pad * 2),
      height: Math.min(window.innerHeight - Math.max(0, r.top - pad), r.height + pad * 2)
    };
  })()`);
}

async function unionBox(cdp, selectors) {
  return evaluate(cdp, `(() => {
    const sels = ${JSON.stringify(selectors)};
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    let found = false;
    for (const s of sels) {
      const el = document.querySelector(s);
      if (!el) continue;
      found = true;
      const r = el.getBoundingClientRect();
      minX = Math.min(minX, r.left);
      minY = Math.min(minY, r.top);
      maxX = Math.max(maxX, r.right);
      maxY = Math.max(maxY, r.bottom);
    }
    if (!found) return null;
    const pad = 16;
    const x = Math.max(0, minX - pad);
    const y = Math.max(0, minY - pad);
    return {
      x, y,
      width: Math.min(window.innerWidth - x, maxX - minX + pad * 2),
      height: Math.min(window.innerHeight - y, maxY - minY + pad * 2)
    };
  })()`);
}

async function shotIndex(cdp) {
  await evaluate(cdp, `(() => {
    document.documentElement.setAttribute('data-theme', 'dark');
    const tabbar = document.querySelector('.tabbar');
    if (tabbar) tabbar.style.display = 'none';
    location.hash = '#fahras';
    document.getElementById('tab-fahras')?.click();
    const search = document.getElementById('filterSearch');
    search.value = 'القرن أعظم';
    search.dispatchEvent(new Event('input', { bubbles: true }));
    const cards = [...document.querySelectorAll('#cards .card')].filter(c => !c.classList.contains('is-hidden'));
    const card = cards[0] || document.querySelector('.card[data-unit-id="2_255_d07"]');
    if (!card) throw new Error('index card not found');
    const panel = card.querySelector('[data-diff-panel]');
    const toggle = card.querySelector('[data-diff-toggle]');
    if (panel) panel.classList.add('is-open');
    if (toggle) toggle.textContent = 'اخفِ الفروق';
    card.scrollIntoView({ block: 'center', behavior: 'auto' });
    return card.dataset.unitId || 'ok';
  })()`);
  await delay(400);
  // Include search field + matching card so the filled query is visible
  const clip = await evaluate(cdp, `(() => {
    const search = document.getElementById('filterSearch');
    const card = [...document.querySelectorAll('#cards .card')].find(c => !c.classList.contains('is-hidden'));
    if (!card) return null;
    card.scrollIntoView({ block: 'end', behavior: 'auto' });
    const a = (search?.closest('.filters') || search)?.getBoundingClientRect();
    const b = card.getBoundingClientRect();
    const pad = 10;
    const top = Math.max(0, Math.min(a ? a.top : b.top, b.top) - pad);
    const bottom = Math.min(window.innerHeight, Math.max(a ? a.bottom : b.bottom, b.bottom) + pad);
    const left = Math.max(0, Math.min(a ? a.left : b.left, b.left) - pad);
    const right = Math.min(window.innerWidth, Math.max(a ? a.right : b.right, b.right) + pad);
    // Prefer showing the card; if too tall, prioritize card
    let y = top;
    let height = bottom - top;
    if (height > window.innerHeight - 8) {
      y = Math.max(0, b.top - pad);
      height = Math.min(window.innerHeight - 8, b.height + pad * 2);
    }
    return { x: left, y, width: right - left, height };
  })()`);
  await captureClip(cdp, join(SHOTS, "shot_index.png"), clip);
}

async function shotReconcile(cdp) {
  await evaluate(cdp, `(() => {
    document.documentElement.setAttribute('data-theme', 'dark');
    const tabbar = document.querySelector('.tabbar');
    if (tabbar) tabbar.style.display = 'none';
    document.getElementById('tab-mutabaqa')?.click();
    const radio = document.querySelector('input[name="rc-set"][value="excel"]');
    if (radio) { radio.checked = true; radio.dispatchEvent(new Event('change', { bubbles: true })); }
    const unitBtn = document.querySelector('#rc-units [data-unit="AK-007"]');
    if (unitBtn) unitBtn.click();
    return !!document.getElementById('rc-compare');
  })()`);
  await delay(300);
  await evaluate(cdp, `document.getElementById('rc-compare').click()`);
  await delay(1100);
  await evaluate(cdp, `(() => {
    const panes = document.querySelector('.rc-panes');
    if (panes) panes.scrollIntoView({ block: 'center', behavior: 'auto' });
    document.querySelectorAll('.rc-body').forEach(b => {
      const mark = b.querySelector('.rc-mark, .rc-loc');
      if (mark) b.scrollTop = Math.max(0, mark.offsetTop - 40);
    });
  })()`);
  await delay(200);
  const clip = await unionBox(cdp, [".rc-panes", "#rc-finding"]);
  await captureClip(cdp, join(SHOTS, "shot_reconcile.png"), clip || await unionBox(cdp, [".rc-panes"]));
}

async function shotExperiment(cdp) {
  // Temporarily taller viewport so pipeline + facts + chart fit
  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width: VIEWPORT.width,
    height: 1400,
    deviceScaleFactor: VIEWPORT.deviceScaleFactor,
    mobile: false,
  });
  await evaluate(cdp, `(() => {
    document.documentElement.setAttribute('data-theme', 'dark');
    const tabbar = document.querySelector('.tabbar');
    if (tabbar) tabbar.style.display = 'none';
    document.getElementById('tab-tajruba')?.click();
  })()`);
  await delay(300);
  const clip = await evaluate(cdp, `(() => {
    const roots = [
      document.querySelector('#panel-tajruba .pipe')?.closest('section'),
      document.querySelector('#facts')?.closest('section'),
      document.querySelector('.chart-card')
    ].filter(Boolean);
    if (!roots.length) return null;
    roots[0].scrollIntoView({ block: 'start', behavior: 'auto' });
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const el of roots) {
      const r = el.getBoundingClientRect();
      minX = Math.min(minX, r.left);
      minY = Math.min(minY, r.top);
      maxX = Math.max(maxX, r.right);
      maxY = Math.max(maxY, r.bottom);
    }
    const pad = 12;
    const x = Math.max(0, minX - pad);
    const y = Math.max(0, minY - pad);
    return {
      x, y,
      width: Math.min(window.innerWidth - x, maxX - minX + pad * 2),
      height: Math.min(window.innerHeight - y, maxY - minY + pad * 2)
    };
  })()`);
  await captureClip(cdp, join(SHOTS, "shot_experiment.png"), clip);
  await setViewport(cdp);
}

async function shotKaab(cdp) {
  await evaluate(cdp, `(() => {
    document.documentElement.setAttribute('data-theme', 'dark');
    const tabbar = document.querySelector('.tabbar');
    if (tabbar) tabbar.style.display = 'none';
    document.getElementById('tab-fahras')?.click();
    const chip = document.querySelector('#exampleChips [data-example="isra"]');
    if (!chip) throw new Error('isra chip missing');
    chip.click();
    const cards = [...document.querySelectorAll('#cards .card')].filter(c => !c.classList.contains('is-hidden'));
    const card = cards[0];
    if (!card) throw new Error('no isra cards');
    const why = card.querySelector('details.why');
    if (why) why.open = true;
    card.scrollIntoView({ block: 'center', behavior: 'auto' });
    return card.dataset.unitId;
  })()`);
  await delay(400);
  const clip = await evaluate(cdp, `(() => {
    const chips = document.getElementById('exampleChips');
    const card = [...document.querySelectorAll('#cards .card')].find(c => !c.classList.contains('is-hidden'));
    if (!card) return null;
    card.scrollIntoView({ block: 'center', behavior: 'auto' });
    const a = chips?.getBoundingClientRect();
    const b = card.getBoundingClientRect();
    const pad = 10;
    // Card is primary; include chips if they still fit above without crushing the card
    let y = Math.max(0, b.top - pad);
    let height = Math.min(window.innerHeight - 8, b.height + pad * 2);
    if (a && a.bottom < b.top && (b.bottom - a.top + pad * 2) <= window.innerHeight) {
      y = Math.max(0, a.top - pad);
      height = Math.min(window.innerHeight - 8, b.bottom - a.top + pad * 2);
    }
    const left = Math.max(0, Math.min(a ? a.left : b.left, b.left) - pad);
    const right = Math.min(window.innerWidth, Math.max(a ? a.right : b.right, b.right) + pad);
    return { x: left, y, width: right - left, height };
  })()`);
  await captureClip(cdp, join(SHOTS, "shot_kaab.png"), clip);
}

async function printPdf(chromePath) {
  // Prefer CDP print for CSS page size control
  const userData = join(DECK, ".chrome-pdf-profile");
  mkdirSync(userData, { recursive: true });
  const port = PORT + 17;
  const args = [
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${userData}`,
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions",
    "--headless=new",
    "--disable-gpu",
    "about:blank",
  ];
  const child = spawn(chromePath, args, { stdio: "ignore" });
  try {
    const cdp = await connectPage(port);
    const fileUrl = pathToFileURL(DECK_HTML).href;
    await cdp.send("Page.navigate", { url: fileUrl });
    await new Promise((resolve) => {
      const t = setTimeout(resolve, 8000);
      cdp.on("Page.loadEventFired", () => { clearTimeout(t); resolve(); });
    });
    // Wait for fonts
    await evaluate(cdp, `document.fonts ? document.fonts.ready.then(() => true) : true`);
    await delay(600);
    const pdf = await cdp.send("Page.printToPDF", {
      printBackground: true,
      preferCSSPageSize: true,
      paperWidth: 1920 / 96,
      paperHeight: 1080 / 96,
      marginTop: 0,
      marginBottom: 0,
      marginLeft: 0,
      marginRight: 0,
      scale: 1,
    });
    writeFileSync(DECK_PDF, Buffer.from(pdf.data, "base64"));
    cdp.close();
  } finally {
    child.kill();
  }
}

function pngSize(path) {
  const buf = readFileSync(path);
  if (buf.length < 24 || buf.toString("ascii", 1, 4) !== "PNG") return { w: 0, h: 0, bytes: buf.length };
  return {
    w: buf.readUInt32BE(16),
    h: buf.readUInt32BE(20),
    bytes: buf.length,
  };
}

function pdfPageCount(path) {
  const text = readFileSync(path);
  // Count /Type /Page entries that are not /Pages
  const s = text.toString("latin1");
  const matches = s.match(/\/Type\s*\/Page(?!s)\b/g);
  return matches ? matches.length : 0;
}

async function main() {
  mkdirSync(SHOTS, { recursive: true });
  if (!existsSync(APP)) throw new Error("Missing " + APP);
  if (!existsSync(DECK_HTML)) throw new Error("Missing " + DECK_HTML + " — write deck.html first");

  const chrome = findChrome();
  console.log("Chrome:", chrome);

  const userData = join(DECK, ".chrome-shot-profile");
  mkdirSync(userData, { recursive: true });
  const args = [
    `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${userData}`,
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions",
    "--headless=new",
    "--disable-gpu",
    "--hide-scrollbars",
    "--allow-file-access-from-files",
    "about:blank",
  ];
  const child = spawn(chrome, args, { stdio: "ignore" });

  try {
    const cdp = await connectPage(PORT);
    await setViewport(cdp);

    const appUrl = pathToFileURL(APP).href;
    console.log("Open:", appUrl);
    await cdp.send("Page.navigate", { url: appUrl });
    await new Promise((resolve) => {
      const t = setTimeout(resolve, 10000);
      cdp.on("Page.loadEventFired", () => { clearTimeout(t); resolve(); });
    });
    await waitReady(cdp);
    await evaluate(cdp, `document.fonts ? document.fonts.ready.then(() => true) : true`);

    console.log("shot_index…");
    await shotIndex(cdp);
    console.log("shot_reconcile…");
    await shotReconcile(cdp);
    console.log("shot_experiment…");
    await shotExperiment(cdp);
    console.log("shot_kaab…");
    await shotKaab(cdp);

    cdp.close();
  } finally {
    child.kill();
  }

  console.log("print PDF…");
  await printPdf(chrome);

  // Gates
  const shots = ["shot_index.png", "shot_reconcile.png", "shot_experiment.png", "shot_kaab.png"];
  console.log("\n=== GATES ===");
  for (const name of shots) {
    const p = join(SHOTS, name);
    const st = existsSync(p) ? statSync(p) : null;
    const sz = st && st.size > 0 ? pngSize(p) : { w: 0, h: 0, bytes: 0 };
    console.log(`${name}: exists=${!!st} bytes=${sz.bytes} pixels=${sz.w}x${sz.h}`);
  }
  const pdfStat = existsSync(DECK_PDF) ? statSync(DECK_PDF) : null;
  const pages = pdfStat ? pdfPageCount(DECK_PDF) : 0;
  const mb = pdfStat ? (pdfStat.size / (1024 * 1024)).toFixed(2) : "0";
  console.log(`deck.pdf: exists=${!!pdfStat} size=${mb} MB pages=${pages}`);
  if (!pdfStat || pages !== 8 || pdfStat.size >= 10 * 1024 * 1024) {
    console.error("PDF gate FAILED");
    process.exitCode = 1;
  } else {
    console.log("PDF gate OK");
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
