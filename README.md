<!-- living-readme: last-sync 7bc7843 2026-10-12 -->

<p align="center"><img src="docs/images/cover.jpg" alt="Indexing the methods of classical tafsir" width="100%" /></p>

# فهرس مناهج التفسير — نصٌّ موثَّق، ووسومٌ مُراجَعة
# Tafsir Integrity Index — Verified Text, Reviewed Method Tags

[![CI](https://github.com/drkhaledalrefay-coder/fahras-manahij-al-tafsir/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/drkhaledalrefay-coder/fahras-manahij-al-tafsir/actions/workflows/ci.yml)
[![Code: MIT](https://img.shields.io/badge/code-MIT-2b6cb0.svg)](LICENSE)
[![Tafsir Text: CC BY 4.0](https://img.shields.io/badge/tafsir%20text-CC%20BY%204.0-5b7f3a.svg)](ATTRIBUTION.md)

**A deterministic pilot for structuring classical Quranic tafsir into verified, tagged units without letting artificial intelligence alter a single letter of the source text.**  
**نموذج تطبيقي حتمي لفهرسة وتفكيك نصوص التفسير الكلاسيكية إلى وحدات منهجية موثقة، دون السماح للذكاء الاصطناعي بكتابة أو تعديل حرف واحد من النص المصدر.**

---

### Dated Status / الحالة الراهنة (as of 2026-10-12 / كما في ١٢ أكتوبر ٢٠٢٦)

* **Pilot Scope / نطاق النموذج:** 3 test passages across 4 classical commentaries: Al-Baqarah 2:255 (Ayat al-Kursi), Al-Baqarah 2:102 (Harut & Marut), and an illustrative passage. Source texts prepared for Imam al-Tabari (d. 310 AH), Ibn Kathir, al-Baghawi, and al-Saadi.
* **Human Approval Status / حالة الاعتماد البشري:** **Zero units have been approved by a religious specialist to date.** Any unit marked `approved` in repository demonstration files (e.g. `web/index_data.json`) is strictly synthetic test data for format verification, not scientific validation.
* **Text Integrity / سلامة النص:** **100% of generated units match the pinned source text character-by-character.** Rebuilt directly from deterministic span slices.
* **Pipeline Maturity / حالة مسار المعالجة:** Multi-model classification, deterministic committee chair (threshold 85), verifier sufficiency gate, and grounding contracts are merged and verified by automated tests in `main`.

---

## English

### 1. The Core Idea

Classical tafsir texts are dense, unbroken prose where hadith, Companions' narrations, linguistic grammar, legal deductions, and historical reports intertwine. The Tafsir Integrity Index decomposes this prose into small, structured units tagged along two axes:
1. **Source of Evidence (مصدر الدليل):** Quran by Quran, Prophetic Sunnah, Companions (Sahabah), Successors (Tabi'un), Arabic language, syntactic analysis (I'rab), or the commentator's reasoned synthesis.
2. **Content Type (نوع المحتوى):** Occasions of revelation (Asbab al-Nuzul), legal rulings (Fiqh), rhetoric/eloquence (Balagha), poetry citations, Isra'iliyyat, virtues (Fada'il), hadith attribution/grading (Takhrij), or meaning clarification.

> **Key Guardrail:** The AI structures and classifies; it **never writes**. Models output only span ID boundaries and closed taxonomy codes. Deterministic software rebuilds each unit character-by-character from the pinned source text.

```
Pinned Source Text ──► Spans Cut by Deterministic Code ──► Classifier Model (Proposes Span IDs Only)
                           │                                          │
                           ▼                                          ▼
            Double-Source Reconciler                     Independent Verifier Model (Different Family)
                           │                                          │
                           ▼                                          ▼
                   Verified Baseline ──────────────► Deterministic Committee Chair (Score >= 85)
                                                                      │
                                                                      ▼
                                                       Human Specialist Review Queue
```

---

### 2. Two Control Points for Text Integrity

| Control Point | Mechanism | Where Enforced |
|---|---|---|
| **Point A: Source Intake** | Source text is downloaded deterministically and pinned by **SHA-256**. Author text is isolated from editor footnotes, and cross-matched character-by-character against an independent secondary source. | `data/raw/manifest.json`<br>`src/reconcile.py`<br>`tests/test_textcore.py` |
| **Point B: Post-Tagging** | Classifier models never return text; they emit integer span IDs. A deterministic reconstructor rebuilds every unit from the pinned source and checks strict equality before rendering. | `src/v2_verify.py`<br>`src/v2_selftest.py`<br>`tests/test_phase1b_and_rejoin.py` |

---

### 3. Pilot Routing Results (Run 2 — Routing Counts, Not Accuracy)

The following figures represent automated routing decisions by the deterministic checker across 3 verses. They are **routing metrics, not accuracy rates**:

| Tafsir / Commentator | Classifier Model | Total Moves | Automated Candidate (Score ≥ 85) | Directed to Specialist Queue |
|---|---|---:|---:|---:|
| **Al-Tabari (d. 310 AH)** | DeepSeek (+ MiMo for 2:255) | 31 | 18 | 13 |
| **Ibn Kathir** | Codex | 42 | 23 | 19 |
| **Ibn Kathir** | DeepSeek | 44 | 26 | 18 |
| **Al-Baghawi** | DeepSeek | 39 | 29 | 10 |
| **Al-Saadi** | DeepSeek | 24 | 15 | 9 |

---

### 4. Repository Layout

| Directory / File | Description |
|---|---|
| `src/` | Core extraction, span partitioning, classification adapter, committee chair, and static site builders |
| `data/` | Pinned source texts, span boundaries, and model outputs (`data/v2/`, `data/multi/`, `data/raw/`) |
| `method/` | Methodological taxonomy (`taxonomy.md`), model instructions, and agent prompts |
| `web/` | Standalone browser reader (`web/fahras.html`) and legacy comparison view (`web/methods.html`) |
| `docs/` | Engineering audit, AI disclosures, execution guides, and branch handoff documentation |
| `tests/` | 12 unit and integration test files covering text safety, classification API, and committee chair |

---

### 5. Where to Verify Claims

| Claim / Component | Evidence / Source Code | Verification Command |
|---|---|---|
| **Text Integrity (Zero altered letters)** | `src/v2_selftest.py`, `tests/test_textcore.py` | `python src/v2_selftest.py` |
| **Committee Chair Logic (Threshold 85)** | `src/committee_chair.py`, `tests/test_committee_chair.py` | `python -m unittest tests.test_committee_chair -v` |
| **Grounding Verifier & Packet Hash** | `src/grounding_verifier.py`, `tests/test_grounding_verifier.py` | `python -m unittest tests.test_grounding_verifier -v` |
| **Classification API Adapter** | `src/classify_api.py`, `tests/test_classify_api.py` | `python -m unittest tests.test_classify_api -v` |
| **Export Schema Compliance** | `schema/export.schema.json`, `tests/test_export_approved.py` | `python -m unittest tests.test_export_approved -v` |
| **Headless Browser Integration** | `deck/qa/qa_runner.py` (Playwright suite) | `python deck/qa/qa_runner.py` |
| **Prior Work Baseline** | Pinned commit `ec616f4` (documented in repo history) | `git log ec616f4` |

---

### 6. Installation & Execution

#### Prerequisites
* Python 3.11 or newer
* Node-free environment (the reader runs as a static zero-dependency web page)

```bash
# 1. Clone repository and setup environment
git clone https://github.com/drkhaledalrefay-coder/fahras-manahij-al-tafsir.git
cd fahras-manahij-al-tafsir
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux / macOS
# source .venv/bin/activate

# 2. Install pinned dependencies
pip install -r requirements.txt

# 3. Execute test gates
python src/v2_selftest.py
python -m unittest discover tests -v
```

#### Launching the Static Reader
```bash
# Build the data index
python src/build_fahras.py

# Serve locally
python -m http.server 8791 --directory web
```
Open your browser at `http://127.0.0.1:8791/fahras.html`.

---

### 7. AI Disclosure & Scholarly Bounds

* **No models were trained:** All classifications utilize foundation models prompting against strict JSON schemas emitting only span ID selections.
* **Models Utilized in Repository Data:** DeepSeek v4.1 flash (`moves/deepseek/`), MiMo v2.6 flash (`data/multi/al_tabari/moves/mimo/`), Codex `gpt-6-sol` (`data/v2/moves/codex/`), and Grok (`data/tags/grok/`).
* **Scholarly Authority:** This tool does not generate tafsir, provide rulings, or arbitrate religious debates. Abu Ja'far al-Tabari (d. 310 AH) is the primary baseline for early exegesis; Ibn Kathir, al-Baghawi, and al-Saadi demonstrate the cross-era generalizability of the tagging taxonomy.

---

### 8. Sources and Licences

* **Code:** MIT License — see [`LICENSE`](LICENSE).
* **Tafsir Source Texts & Derived Data:** CC BY 4.0 with mandatory attribution to **Tafsir Center for Quranic Studies (مركز تفسير للدراسات القرآنية)** (`tafsircenter/tafsir-mcp-data`). Non-commercial research distribution.
* **Database Note:** The primary database `quran.db` (~234 MB) is not tracked in git; it is fetched deterministically and verified via `data/raw/manifest.json`.

---

## العربية

### ١. الفكرة الأساسية

كتب التفسير نصوص متصلة زاخرة بالحديث، والأثر، والاستشهاد اللغوي، والترجيح الفقهي، والإسرائيليات. يقوم «فهرس مناهج التفسير» بتفكيك هذا النص إلى وحدات صغيرة محددة، موسومة بمحورين:
1. **مصدر الدليل:** قرآن بقرآن، سنة، صحابة، تابعون، لغة، إعراب، رأي المفسر واجتهاده.
2. **نوع المحتوى:** أسباب نزول، فقه، بلاغة، شواهد شعرية، إسرائيليات، فضائل، تخريج، بيان معنى.

> **الضابط الحاكم:** الذكاء الاصطناعي **يرتب ولا يكتب**. لا يولد النموذج أي نص حر، بل يقتصر على إرجاع معرفات الأجزاء (Span IDs) ورموز التصنيف المغلقة، بينما يتولى كود حتمي إعادة بناء النص حرفاً بحرف من النسخة المثبتة ببصمة إلكترونية.

---

### ٢. نقطتا تحكم لضمان سلامة النص

| نقطة التحكم | آلية العمل | موضع التحقق |
|---|---|---|
| **(أ) قبول المصدر** | يُنزَّل النص آلياً وتُثبت بصمته الإلكترونية (SHA-256). يُفصل كلام المؤلف عن حواشي المحقق عبر خوارزمية حتمية، ويُطابق مع نسخة ثانية مستقلة كاشفاً فروق الرقمنة. | `data/raw/manifest.json`<br>`src/reconcile.py`<br>`tests/test_textcore.py` |
| **(ب) ما بعد التصنيف** | يمتنع النموذج عن توليد النص؛ ويُعاد بناء كل وحدة من النص المصدر نفسه وتُطابق حرفاً بحرف قبل العرض على لوحة المراجعة المزدوجة. | `src/v2_verify.py`<br>`src/v2_selftest.py`<br>`tests/test_phase1b_and_rejoin.py` |

---

### ٣. أعداد التوجيه في التشغيل الثاني (Run 2 — أعداد توجيه وليست نسبة دقة)

الأعداد التالية تمثل قرارات التوجيه التي اتخذها الفاحص الحتمي ورئيس اللجنة على ٣ آيات تجريبية، وهي **أعداد توجيه وليست نسب دقة نهائية**:

| التفسير | المصنّف | إجمالي الحركات | مرشّح آلي (درجة ≥ ٨٥) | مُحال لطابور المتخصص |
|---|---|---:|---:|---:|
| **الطبري (ت ٣١٠هـ)** | DeepSeek (+ MiMo لآية 2:255) | ٣١ | ١٨ | ١٣ |
| **ابن كثير** | Codex | ٤٢ | ٢٣ | ١٩ |
| **ابن كثير** | DeepSeek | ٤٤ | ٢٦ | ١٨ |
| **البغوي** | DeepSeek | ٣٩ | ٢٩ | ١٠ |
| **السعدي** | DeepSeek | ٢٤ | ١٥ | ٩ |

---

### ٤. خريطة التحقق من الصحة (Where to Verify)

| الدعوى أو المكون | موضع الدليل في الكود | أمر التحقق الفوري |
|---|---|---|
| **سلامة النص (مطابقة حرفية ١٠٠٪)** | `src/v2_selftest.py` و`tests/test_textcore.py` | `python src/v2_selftest.py` |
| **رئيس اللجنة الحتمي (عتبة ٨٥)** | `src/committee_chair.py` و`tests/test_committee_chair.py` | `python -m unittest tests.test_committee_chair -v` |
| **عقد التحقق وبصمة الحزمة** | `src/grounding_verifier.py` و`tests/test_grounding_verifier.py` | `python -m unittest tests.test_grounding_verifier -v` |
| **محول واجهة التصنيف** | `src/classify_api.py` و`tests/test_classify_api.py` | `python -m unittest tests.test_classify_api -v` |
| **مطابقة مخطط تصدير المعتمد** | `schema/export.schema.json` و`tests/test_export_approved.py` | `python -m unittest tests.test_export_approved -v` |
| **فحص الواجهة بمتصفح آلي** | `deck/qa/qa_runner.py` (Playwright) | `python deck/qa/qa_runner.py` |

---

### ٥. التشغيل وإعادة البناء

```bash
# تهيئة البيئة وتثبيت الاعتماديات
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS
pip install -r requirements.txt

# تشغيل بوابات الاختبار الحتمية
python src/v2_selftest.py
python -m unittest discover tests -v

# بناء فهرس البيانات وتشغيل الخادم المحلي
python src/build_fahras.py
python -m http.server 8791 --directory web
```
افتح المتصفح على: `http://127.0.0.1:8791/fahras.html`.

---

### ٦. الإفصاح عن أدوات الذكاء الاصطناعي والمصادر

* **لم يُدرَّب أي نموذج:** استُخدمت النماذج كمصنفات مقيدة عبر واجهات برمجة التطبيقات باستدعاءات مقيدة بصيغة JSON.
* **المرجعية العلمية:** لا تُنشئ الأداة شروحاً مستقلة ولا تستنبط أحكاماً؛ يتقدم العمل الإمام أبو جعفر الطبري (ت ٣١٠هـ) كأصل أثري مؤسس، وتُعرض تفاسير ابن كثير والبغوي والسعدي كشواهد على تعميم منهجية الفهرسة.
* **التراخيص:** الكود متاح تحت رخصة **MIT**. نصوص التفسير والبيانات المشتقة مرخصة برخصة **CC BY 4.0** مع وجوب النسبة لـ **مركز تفسير للدراسات القرآنية**.
