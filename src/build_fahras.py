"""Build web/fahras.html from src/fahras_template.html + multi-tafsir JSON data.

Read-only over data/. Tolerates missing/partial verified moves.
Does not touch methods_template.html / build_methods.py / web/methods.html.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src" / "fahras_template.html"
OUT = ROOT / "web" / "fahras.html"

DATA_MARKER = "__METHODS_DATA_JSON__"

TAFSIRS = (
    {
        "id": "al_tabari",
        "name": "تفسير الطبري",
        "short": "الطبري",
        "author": "محمد بن جرير الطبري",
        "base": ROOT / "data" / "multi" / "al_tabari",
        "windows_map": {
            "2_255": "2_255",
            "2_102": "2_102",
            "17_105": "17_105",
        },
        "layers_dir": ROOT / "data" / "multi" / "al_tabari" / "layers",
        "layers_map": {
            "2_255": "2_255",
            "2_102": "2_102",
            "17_105": "17_105",
        },
        "raw_prefix": ROOT / "data" / "raw" / "tafsircenter" / "al_tabari",
        "raw_in_subdir": True,
    },
    {
        "id": "ibn_kathir",
        "name": "تفسير ابن كثير",
        "short": "ابن كثير",
        "author": "إسماعيل بن عمر بن كثير",
        "base": ROOT / "data" / "v2",
        "windows_map": {
            "2_255": "2_255_tafsir",
            "2_102": "2_102",
            "17_105": "17_105",
        },
        "layers_dir": ROOT / "data" / "layers",
        "layers_map": {
            "2_255": "2_255",
            "2_102": "2_102",
            "17_105": "17_105",
        },
        "raw_prefix": ROOT / "data" / "raw" / "tafsircenter",
        "raw_in_subdir": False,
    },
    {
        "id": "al_baghawi",
        "name": "تفسير البغوي",
        "short": "البغوي",
        "author": "الحسين بن مسعود البغوي",
        "base": ROOT / "data" / "multi" / "al_baghawi",
        "windows_map": {
            "2_255": "2_255",
            "2_102": "2_102",
            "17_105": "17_105",
        },
        "layers_dir": ROOT / "data" / "multi" / "al_baghawi" / "layers",
        "layers_map": {
            "2_255": "2_255",
            "2_102": "2_102",
            "17_105": "17_105",
        },
        "raw_prefix": ROOT / "data" / "raw" / "tafsircenter" / "al_baghawi",
        "raw_in_subdir": True,
    },
    {
        "id": "al_saadi",
        "name": "تفسير السعدي",
        "short": "السعدي",
        "author": "عبد الرحمن بن ناصر السعدي",
        "base": ROOT / "data" / "multi" / "al_saadi",
        "windows_map": {
            "2_255": "2_255",
            "2_102": "2_102",
            "17_105": "17_105",
        },
        "layers_dir": ROOT / "data" / "multi" / "al_saadi" / "layers",
        "layers_map": {
            "2_255": "2_255",
            "2_102": "2_102",
            "17_105": "17_105",
        },
        "raw_prefix": ROOT / "data" / "raw" / "tafsircenter" / "al_saadi",
        "raw_in_subdir": True,
    },
)

WINDOW_ORDER = ("2_255", "2_102", "17_105")
WINDOW_LABELS = {
    "2_255": "آية الكرسي ٢:٢٥٥",
    "2_102": "البقرة ١٠٢",
    "17_105": "الإسراء ١٠٥",
}
# Quran verse text for the reading-column heading (public-domain mushaf wording).
WINDOW_VERSES = {
    "2_255": "ٱللَّهُ لَا إِلَٰهَ إِلَّا هُوَ ٱلْحَىُّ ٱلْقَيُّومُ ۚ لَا تَأْخُذُهُۥ سِنَةٌ وَلَا نَوْمٌ ۚ لَّهُۥ مَا فِى ٱلسَّمَٰوَٰتِ وَمَا فِى ٱلْأَرْضِ ۗ مَن ذَا ٱلَّذِى يَشْفَعُ عِندَهُۥ إِلَّا بِإِذْنِهِۦ ۚ يَعْلَمُ مَا بَيْنَ أَيْدِيهِمْ وَمَا خَلْفَهُمْ ۖ وَلَا يُحِيطُونَ بِشَىْءٍ مِّنْ عِلْمِهِۦ إِلَّا بِمَا شَآءَ ۚ وَسِعَ كُرْسِيُّهُ ٱلسَّمَٰوَٰتِ وَٱلْأَرْضَ ۖ وَلَا يَئُودُهُۥ حِفْظُهُمَا ۚ وَهُوَ ٱلْعَلِىُّ ٱلْعَظِيمُ",
    "2_102": "وَٱتَّبَعُوا۟ مَا تَتْلُوا۟ ٱلشَّيَٰطِينُ عَلَىٰ مُلْكِ سُلَيْمَٰنَ ۖ وَمَا كَفَرَ سُلَيْمَٰنُ وَلَٰكِنَّ ٱلشَّيَٰطِينَ كَفَرُوا۟ يُعَلِّمُونَ ٱلنَّاسَ ٱلسِّحْرَ وَمَآ أُنزِلَ عَلَى ٱلْمَلَكَيْنِ بِبَابِلَ هَٰرُوتَ وَمَٰرُوتَ ۚ وَمَا يُعَلِّمَانِ مِنْ أَحَدٍ حَتَّىٰ يَقُولَآ إِنَّمَا نَحْنُ فِتْنَةٌ فَلَا تَكْفُرْ ۖ فَيَتَعَلَّمُونَ مِنْهُمَا مَا يُفَرِّقُونَ بِهِۦ بَيْنَ ٱلْمَرْءِ وَزَوْجِهِۦ ۚ وَمَا هُم بِضَآرِّينَ بِهِۦ مِنْ أَحَدٍ إِلَّا بِإِذْنِ ٱللَّهِ ۚ وَيَتَعَلَّمُونَ مَا يَضُرُّهُمْ وَلَا يَنفَعُهُمْ ۚ وَلَقَدْ عَلِمُوا۟ لَمَنِ ٱشْتَرَىٰهُ مَا لَهُۥ فِى ٱلْءَاخِرَةِ مِنْ خَلَٰقٍ ۚ وَلَبِئْسَ مَا شَرَوْا۟ بِهِۦٓ أَنفُسَهُمْ ۚ لَوْ كَانُوا۟ يَعْلَمُونَ",
    "17_105": "وَبِٱلْحَقِّ أَنزَلْنَٰهُ وَبِٱلْحَقِّ نَزَلَ ۗ وَمَآ أَرْسَلْنَٰكَ إِلَّا مُبَشِّرًا وَنَذِيرًا",
}


def embed(payload: object) -> str:
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_bytes().decode("utf-8"))


def _read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def _load_window(path: Path) -> dict:
    w = _read_json(path)
    return {
        "window_id": w["window_id"],
        "ayah": w["ayah"],
        "surah": w.get("surah"),
        "ayah_number": w.get("ayah_number"),
        "source_file": w["source_file"],
        "source_sha256": w.get("source_sha256"),
        "window_start": w["window_start"],
        "window_end": w["window_end"],
        "window_text": w["window_text"],
        "spans": w["spans"],
        "apparatus": w.get("apparatus") or [],
        "selection": w.get("selection") or {},
        "span_count": w.get("span_count"),
    }


def _load_markers(path: Path | None) -> dict:
    if path is None or not path.is_file():
        return {
            "family_counts": {},
            "spans": [],
            "editor_footnote_evidence": [],
            "isnad_ranges": [],
        }
    m = _read_json(path)
    return {
        "family_counts": m.get("family_counts") or {},
        "spans": m.get("spans") or [],
        "editor_footnote_evidence": m.get("editor_footnote_evidence") or [],
        "isnad_ranges": m.get("isnad_ranges") or [],
    }


def _load_layers(path: Path | None) -> dict | None:
    if path is None or not path.is_file():
        return None
    return _read_json(path)


def _raw_path(cfg: dict, source_file: str, verse_key: str) -> Path:
    # Prefer path recorded on the window; fall back to conventional layout.
    recorded = ROOT / source_file if not Path(source_file).is_absolute() else Path(source_file)
    if recorded.is_file():
        return recorded
    name = Path(source_file).name
    candidate = cfg["raw_prefix"] / name
    if candidate.is_file():
        return candidate
    return cfg["raw_prefix"] / f"{verse_key}.txt"


def _load_verified(base: Path) -> tuple[dict, list[str], bool]:
    """Return verified[window_key][annotator] = {annotator, moves, summary}, annotators, classifier_ran."""
    verified: dict = {}
    annotators: set[str] = set()
    classifier_ran = False
    vdir = base / "verified"
    if not vdir.is_dir():
        return verified, [], False
    for ann_dir in sorted(p for p in vdir.iterdir() if p.is_dir()):
        if ann_dir.name == "fixture":
            continue
        for path in sorted(ann_dir.glob("*.json")):
            try:
                payload = _read_json(path)
            except (OSError, json.JSONDecodeError):
                # Tolerate partial writes from a concurrent classifier agent.
                continue
            stem = path.stem
            # Normalize IK 2_255_tafsir → 2_255
            key = "2_255" if stem == "2_255_tafsir" else stem
            if key not in WINDOW_ORDER:
                continue
            classifier_ran = True
            annotators.add(ann_dir.name)
            verified.setdefault(key, {})[ann_dir.name] = {
                "annotator": ann_dir.name,
                "moves": payload.get("moves") or [],
                "summary": payload.get("summary") or {},
            }
    return verified, sorted(annotators), classifier_ran


def _load_run1_totals(base: Path) -> dict:
    """Sum auto/specialist from verified_run1 snapshot (pre–strict verifier)."""
    auto = 0
    specialist = 0
    vdir = base / "verified_run1"
    if not vdir.is_dir():
        return {"auto": 0, "specialist": 0}
    for ann_dir in sorted(p for p in vdir.iterdir() if p.is_dir()):
        if ann_dir.name == "fixture":
            continue
        for path in sorted(ann_dir.glob("*.json")):
            try:
                payload = _read_json(path)
            except (OSError, json.JSONDecodeError):
                continue
            stem = path.stem
            key = "2_255" if stem == "2_255_tafsir" else stem
            if key not in WINDOW_ORDER:
                continue
            for m in payload.get("moves") or []:
                if m.get("route") == "auto_candidate":
                    auto += 1
                else:
                    specialist += 1
    return {"auto": auto, "specialist": specialist}


def _assert_spans_match_raw(windows: dict, raw: dict, tafsir_id: str) -> None:
    for wid, w in windows.items():
        r = raw.get(wid)
        if not r:
            raise SystemExit(f"{tafsir_id}/{wid}: missing raw slice")
        full = r["full_text"]
        for sp in w.get("spans") or []:
            start, end = sp["start"], sp["end"]
            got = full[start:end]
            if got != sp["text"]:
                raise SystemExit(
                    f"{tafsir_id}/{wid} span {sp.get('id')} text != raw[{start}:{end}]"
                )
            # Also equal window_text relative slice when inside window.
            if w["window_start"] <= start < end <= w["window_end"]:
                rel = w["window_text"][start - w["window_start"] : end - w["window_start"]]
                if rel != sp["text"]:
                    raise SystemExit(
                        f"{tafsir_id}/{wid} span {sp.get('id')} text != window_text slice"
                    )


def collect_tafsir(cfg: dict) -> dict:
    tid = cfg["id"]
    base: Path = cfg["base"]
    windows: dict = {}
    markers: dict = {}
    layers: dict = {}
    raw: dict = {}

    for verse_key, file_stem in cfg["windows_map"].items():
        wpath = base / "windows" / f"{file_stem}.json"
        if not wpath.is_file():
            raise SystemExit(f"missing window {tid}/{verse_key}: {wpath}")
        w = _load_window(wpath)
        # Canonical key for the page selector.
        w["verse_key"] = verse_key
        windows[verse_key] = w

        mpath = base / "markers" / f"{file_stem}.json"
        markers[verse_key] = _load_markers(mpath if mpath.is_file() else None)

        layer_stem = cfg["layers_map"][verse_key]
        layers[verse_key] = _load_layers(cfg["layers_dir"] / f"{layer_stem}.json")

        rpath = _raw_path(cfg, w["source_file"], verse_key)
        if not rpath.is_file():
            raise SystemExit(f"missing raw source {tid}/{verse_key}: {rpath}")
        full = _read_text(rpath)
        slice_text = full[w["window_start"] : w["window_end"]]
        if slice_text != w["window_text"]:
            raise SystemExit(
                f"{tid}/{verse_key}: raw[{w['window_start']}:{w['window_end']}] != window_text"
            )
        raw[verse_key] = {
            "text": slice_text,
            "full_text": full,
            "source_sha256": w.get("source_sha256"),
            "source_file": w["source_file"],
            "window_start": w["window_start"],
            "window_end": w["window_end"],
        }

    verified, annotators, classifier_ran = _load_verified(base)
    run1_totals = _load_run1_totals(base)
    _assert_spans_match_raw(windows, raw, tid)

    # Drop full_text from embedded payload (large); keep window slice only.
    raw_embed = {
        k: {
            "text": v["text"],
            "source_sha256": v["source_sha256"],
            "source_file": v["source_file"],
            "window_start": v["window_start"],
            "window_end": v["window_end"],
        }
        for k, v in raw.items()
    }

    return {
        "id": tid,
        "name": cfg["name"],
        "short": cfg["short"],
        "author": cfg.get("author") or "",
        "windows": windows,
        "markers": markers,
        "layers": layers,
        "verified": verified,
        "raw": raw_embed,
        "annotators": annotators,
        "classifier_ran": classifier_ran,
        "run1_totals": run1_totals,
    }


def _sha12(hexdigest: str | None) -> str:
    if not hexdigest:
        return ""
    return hexdigest[:12]


def _build_sources(tafsirs: dict) -> dict:
    out = {}
    for cfg in TAFSIRS:
        tid = cfg["id"]
        t = tafsirs[tid]
        verses = {}
        for verse_key in WINDOW_ORDER:
            raw = (t.get("raw") or {}).get(verse_key) or {}
            block = (t.get("verified") or {}).get(verse_key) or {}
            models = sorted(block.keys())
            verses[verse_key] = {
                "sha256_12": _sha12(raw.get("source_sha256")),
                "models": models,
                "label": WINDOW_LABELS.get(verse_key, verse_key),
            }
        out[tid] = {
            "id": tid,
            "name": t["name"],
            "author": t.get("author") or cfg.get("author") or "",
            "digital_source": "مركز تفسير — بيانات مفتوحة",
            "digital_repo": "tafsircenter/tafsir-mcp-data",
            "license": "CC BY 4.0",
            "printed_edition": "غير محددة في بيانات المصدر — قيد التحقق",
            "verses": verses,
        }
    return out


def _build_coverage(tafsirs: dict) -> dict:
    """One annotator per tafsir×verse (most moves, then name) to avoid multi-model double-count."""
    moves = 0
    ayahs: set[str] = set()
    tafsir_ids: set[str] = set()
    for tid, t in tafsirs.items():
        for wid in WINDOW_ORDER:
            if wid not in (t.get("windows") or {}):
                continue
            block = (t.get("verified") or {}).get(wid) or {}
            if not block:
                continue
            best_n = -1
            best_moves: list = []
            for ann in sorted(block.keys()):
                mlist = block[ann].get("moves") or []
                n = len(mlist)
                if n > best_n:
                    best_n = n
                    best_moves = mlist
            if best_n > 0:
                moves += best_n
                ayahs.add(wid)
                tafsir_ids.add(tid)
    return {
        "moves": moves,
        "ayahs": len(ayahs) if ayahs else len(WINDOW_ORDER),
        "tafsirs": len(tafsir_ids) if tafsir_ids else len(tafsirs),
        "label": f"{moves} موضعاً في {len(ayahs) if ayahs else len(WINDOW_ORDER)} آيات عبر {len(tafsir_ids) if tafsir_ids else len(tafsirs)} تفاسير",
    }


def collect_data() -> dict:
    tafsirs = {}
    for cfg in TAFSIRS:
        tafsirs[cfg["id"]] = collect_tafsir(cfg)
    sources = _build_sources(tafsirs)
    coverage = _build_coverage(tafsirs)
    payload = {
        "tafsirs": tafsirs,
        "tafsir_order": [c["id"] for c in TAFSIRS],
        "tafsir_labels": {c["id"]: c["short"] for c in TAFSIRS},
        "default_tafsir": "al_tabari",
        "default_window": "2_255",
        "window_order": list(WINDOW_ORDER),
        "window_labels": dict(WINDOW_LABELS),
        "window_verses": dict(WINDOW_VERSES),
        # Flat aliases filled by the page JS for the active tafsir —
        # also pre-seeded to al_tabari so a partial boot still works.
        "windows": tafsirs["al_tabari"]["windows"],
        "markers": tafsirs["al_tabari"]["markers"],
        "verified": tafsirs["al_tabari"]["verified"],
        "layers": tafsirs["al_tabari"]["layers"],
        "raw": tafsirs["al_tabari"]["raw"],
        "classifier_ran": tafsirs["al_tabari"]["classifier_ran"],
        "tafsir": {
            "id": tafsirs["al_tabari"]["id"],
            "name": tafsirs["al_tabari"]["name"],
        },
        "annotators": tafsirs["al_tabari"]["annotators"],
        "sources": sources,
        "coverage": coverage,
        "integrity_rule": "لم يُغيَّر حرف من النص",
    }
    # Version stamps the payload *before* embedding the stamps themselves.
    core = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    payload["data_version"] = hashlib.sha256(core.encode("utf-8")).hexdigest()[:12]
    payload["build_date"] = date.today().isoformat()
    return payload


def check_html(html: str) -> None:
    if not html.startswith('<meta charset="utf-8">'):
        raise SystemExit("fahras.html must start with charset meta")
    if "\r" in html:
        raise SystemExit("fahras.html must use LF newlines")
    lowered = html.lower()
    for token in ("<!doctype", "<html", "</html", "<head>", "<head ", "</head", "<body", "</body"):
        if token in lowered:
            raise SystemExit(f"forbidden markup: {token}")
    urls = re.findall(r"(?:href|src)\s*=\s*[\"'](https?://[^\"']+)", html, flags=re.I)
    urls += re.findall(r"url\(\s*[\"']?(https?://[^)\"']+)", html, flags=re.I)
    allowed = ("fonts.googleapis.com", "tafsir.net", "dorar.net", "quran.com")
    bad = [url for url in urls if not any(a in url for a in allowed)]
    if bad:
        raise SystemExit("unexpected external URL: " + ", ".join(bad))
    if "fonts.googleapis.com" not in html:
        raise SystemExit("missing Google Fonts stylesheet")
    if DATA_MARKER in html:
        raise SystemExit("data marker not replaced")
    stripe = re.findall(
        r"border-(?:inline-start|inline-end|left|right)\s*:\s*([0-9.]+)px",
        html,
        flags=re.I,
    )
    wide = [x for x in stripe if float(x) > 1]
    if wide:
        raise SystemExit(f"side-stripe borders >1px found: {wide}")


def _check_br_source_fidelity(tafsirs: dict) -> None:
    """Simulate pane reconstruction: <br> slices stay as source chars; concat == raw."""
    failures: list[str] = []
    n = 0
    for tid, t in tafsirs.items():
        for wid in WINDOW_ORDER:
            w = (t.get("windows") or {}).get(wid)
            raw = (t.get("raw") or {}).get(wid)
            if not w or not raw:
                failures.append(f"{tid}/{wid}: missing window or raw")
                continue
            text = w["window_text"]
            expect = raw["text"]
            n += 1
            if text != expect:
                failures.append(f"{tid}/{wid}: window_text != raw.text")
                continue
            # Split keeping "<br>" as its own source run (same as UI makeLayoutBreak).
            parts: list[str] = []
            i = 0
            while i < len(text):
                j = text.find("<br>", i)
                if j < 0:
                    parts.append(text[i:])
                    break
                if j > i:
                    parts.append(text[i:j])
                parts.append("<br>")
                i = j + 4
            got = "".join(parts)
            if got != expect:
                failures.append(
                    f"{tid}/{wid}: br-run concat mismatch "
                    f"(got {len(got)} / expect {len(expect)})"
                )
            # Default annotator for window: first preferred with verified moves.
            block = (t.get("verified") or {}).get(wid) or {}
            pref = ("codex", "deepseek", "mimo")
            avail = [
                a
                for a in pref
                if a in block and (block[a].get("moves") or [])
            ]
            others = sorted(
                a
                for a in block
                if a not in pref and (block[a].get("moves") or [])
            )
            default_ann = (avail + others)[0] if (avail or others) else None
            if tid == "al_tabari" and wid == "2_255" and default_ann != "mimo":
                failures.append(
                    f"al_tabari/2_255 default annotator={default_ann!r} (expected mimo)"
                )
    if failures:
        raise SystemExit(
            "br/source fidelity self-test FAILED:\n  " + "\n  ".join(failures)
        )
    print(f"br/source fidelity self-test PASS ({n} windows)")


def build() -> Path:
    if not TEMPLATE.is_file():
        raise SystemExit(f"missing template {TEMPLATE}")
    data = collect_data()
    _check_br_source_fidelity(data["tafsirs"])
    html = TEMPLATE.read_bytes().decode("utf-8")
    if "\r\n" in html:
        html = html.replace("\r\n", "\n")
    if DATA_MARKER not in html:
        raise SystemExit("template missing data marker")
    html = html.replace(DATA_MARKER, embed(data))
    check_html(html)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(html.encode("utf-8"))
    n_verified = sum(
        1
        for t in data["tafsirs"].values()
        for _wid, anns in t["verified"].items()
        for _ in anns
    )
    print(
        f"wrote {OUT.relative_to(ROOT).as_posix()} "
        f"({OUT.stat().st_size} bytes) "
        f"tafsirs={len(data['tafsirs'])} verified_files={n_verified} "
        f"data_version={data.get('data_version')} "
        f"coverage={data.get('coverage', {}).get('label', '')}"
    )
    return OUT


def _enable_utf8_stdout() -> None:
    """Keep Arabic summary printable on consoles with a legacy code page."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


if __name__ == "__main__":
    _enable_utf8_stdout()
    build()
