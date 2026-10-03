# إصلاحات التدقيق — ٢٠٢٦-١٠-٠٣

مرجع: [`AUDIT_2026-10-02.md`](AUDIT_2026-10-02.md). فرع العمل: `build/audit-fixes`. الجزء ١ (تقني).

`data_version` قبل البدء وبعده: **`4bf26ce1d03a`** (لا تغيير).

---

## ١. بناء حتمي لـ `web/fahras.html`

**السبب الجذري:** `payload["build_date"] = date.today().isoformat()` يُدمَج داخل `<script id="methods-data">`، فتتغيّر البايتات عند اختلاف اليوم عن الختم المخزَّن. كذلك `embed()` كان بلا `sort_keys` فيعتمد ترتيب مفاتيح القاموس على ترتيب الإدراج.

**قبل:** إعادة البناء تغيّر JSON المضمَّن (`build_date` على الأقل).  
**بعد:**
- `embed(..., sort_keys=True)`
- `_stable_build_date`: `SOURCE_DATE_EPOCH` إن وُجد، وإلا إعادة ختم `build_date` السابق عند ثبات `data_version`، وإلا تاريخ اليوم

**قبول:** بناء → نسخ → بناء → تطابق بايتات (`cmp identical: True`، الحجم `1318029`).

---

## ٢. وحدة `src/textcore.py` (المرحلة ٢٫١)

**قبل:** `_read_exact` ×١٠، `_read_json` ×٩، `_sha256_*` ×٥، `_assert_tiling` ×٣ (أجسام متباعدة مع `assert`)، `_resolve_base` ×٣.  
**بعد:** نسخة واحدة: `read_exact`، `read_json`، `sha256_bytes` / `sha256_file`، `assert_tiling` (الأشد + `IntegrityError`)، `resolve_base`. الاستيراد من كل الملفات التي كانت تنسخها. اختبارات في `tests/test_textcore.py`.

**قبول:**
- `grep "^def _read_exact" src/*.py` → **٠**
- `data_version` بعد البناء = **`4bf26ce1d03a`**
- `pytest`: ٦٢ ناجح، ٢ متخطّى

---

## ٣. CI (المرحلة ٣٫٣)

**قبل:** لا يوجد `.github/`.  
**بعد:** `.github/workflows/ci.yml` على `ubuntu-latest` / Python 3.12: `pip install -r requirements.txt` + pytest، `python src/v2_selftest.py`، بناء مرتين + `cmp`.

**مراجعة PART 3:** خطوتان منفصلتان لمسارات التجميد `data/**/{raw,layers,spans,windows}` فقط (لا `data/multi` كاملاً): (1) فرق مقابل قاعدة الـ PR (`origin/${{ github.base_ref }}...HEAD`) أو `HEAD~1` على push؛ (2) نظافة ما بعد البناء (`git diff` على الشجرة العاملة).

---

## ٤. قياس الحمولة (المرحلة ٣٫١)

**المنهج (محلي، ٢٠٢٦-١٠-٠٣):**
- الحجم الخام: `len(web/fahras.html.read_bytes())`
- المضغوط: `gzip.compress(..., compresslevel=9)` (ومستوى gzip الافتراضي أعطى الرقم نفسه)
- زمن التحميل: Chromium عبر Playwright، `wait_until="load"`، بعد إحماء، وسيط ٣ عيّنات؛ خادم `http.server` على `127.0.0.1`

| المقياس | القيمة |
|---|---:|
| خام | **١٬٣١٨٬٠٢٩** بايت (≈ ١٫٢٦ ميبيبايت) |
| gzip | **٢٣٥٬٢١٥** بايت (≈ ٢٣٠ كيبيبايت) |
| load 1440×900 (وسيط) | **٥٦٦٫٤** م.ث |
| load 390×844 (وسيط) | **٤٩٥٫٧** م.ث |

**قبل/بعد الإصلاحات التقنية أعلاه:** الأرقام في نطاق قياس التدقيق السابق (~١٫٣٢ م.ب خاماً، ~٢٣٣ ك.ب مضغوطاً، ~٥٦٥/~٤٥٠ م.ث). **لم تُضف أنفال**؛ عتبة التقسيم (٥٠٠ ك.ب مضغوطة أو ثانيتان) **لم تُبلَغ** — لا تقسيم JSON في هذا الجزء.

---

## ٥. بقايا textcore + سكربتات يتيمة (الجزء ٢)

**قبل:** `src/build_reconcile.py` ما زال يعرّف `read_exact` محلياً.  
**بعد:** يستورد من `textcore`؛ `grep "^def _read_exact\|^def read_exact"` → التعريف الوحيد في `src/textcore.py`.

فحوص ذات معنى حُوّلت إلى pytest دون حذف الأصول:
- `tests/test_phase1b_and_rejoin.py` يغطي منطق `check_phase1b` و`check_spans_rejoin`.

### بانتظار قرار الفريق

- `src/check_phase1b.py` و`src/check_spans_rejoin.py` ما زالا في `src/` (لم يُحذفا ولم يُنقلا إلى `archive/`). القرار: إبقاء كمداخل يدوية، أو أرشفة بعد الاعتماد على الاختبارات الجديدة.

---

## ٦. QA T9–T15 (اختبارات قديمة لا تراجع واجهة)

**الحكم:** اختبارات متقادمة، لا انحدار واجهة.  
**الدليل:** قبل الإصلاح، نقر Playwright يفشل بمهلة لأن `#drawer-backdrop` / `#drawer` يعترضان بعد `selectHighlight()` عند الإضافة؛ لقطات الفشل في `deck/qa/shots/*_T9_fail` وما يليها، والسجل يظهر `intercepts pointer events`. الواجهة تفتح الدرج تلقائياً بعد «إضافة إلى التعليق».

**قبل:** T9–T15 (+ T14 في نفس الجلسة) FAIL.  
**بعد (طبقة الاختبار `deck/qa/qa_runner.py`):** سحب فأرة للتحديد، مقارنة/اعتماد من الدرج دون إعادة نقر العلامة تحت الخلفية، و`close_drawer` قبل T10–T15. T1: تجاهل 404 لـ `favicon.ico` فقط.

**مراجعة PART 3:** `close_drawer` يسجّل فشل التنظيف ولا يبتلعه؛ مع `require_closed=True` (الافتراضي قبل الفحوص التالية) يُثبت أن الدرج/الخلفية مغلقان.

**قبول:** T9–T15 PASS؛ خروج `qa_runner` ٠ بعد تصفية favicon.

---

## ٧. قرارات الاعتماد — تصميم + استيراد بلا تغيير مخطط

- مقترح: `docs/DECISIONS_PROPOSAL.md` + قسم في `docs/RUN.md`
- تنفيذ بلا تغيير schema: `src/import_reviews.py` + `tests/test_import_reviews.py`
- **`--out-root` مطلوب** (لا افتراضي لجذر المستودع)
- Fixture الاستيراد: نص مثبّت **ملفّق** يُبنى في `tmp_path` داخل الاختبار (لا نص تفسير تحت `tests/`)

---

## ٨. تجهيز النشر (بدون نشر)

- `netlify.toml` (`publish = "web"` + ترويسات)
- `docs/DEPLOY.md` (يشمل قضية `<!doctype>` / `lang="ar"` دون تغيير الباني)

---

## ٩. مراجعة PART 3 (مستقل) — إصلاحات

| # | الإصلاح |
|---|---|
| H1 | `--out-root` إلزامي في `import_reviews` + تحديث الوثائق |
| H2 | حذف fixture التفسير؛ بناء مصدر ملفّق + sha256 في الاختبار |
| H3 | فرق مسارات التجميد مقابل قاعدة الـ PR / `HEAD~1` منفصل عن نظافة ما بعد البناء |
| M4 | تجميد `data/**/{raw,layers,spans,windows}` فقط |
| M5 | `close_drawer`: تسجيل الفشل + assert الإغلاق |

---

## ١٠. PART 4 — مغلف تصدير الواجهة الكلاسيكية

**العلّة:** زر «تصدير كل المعتمد» يكتب `{ data_version, records }` بينما `load_records` كان يقبل مصفوفة / `annotations` / سجل واحد فقط → سلسلة الاعتماد→التصدير→التحقق مكسورة على واجهة الفهرس نفسها.

**الإصلاح (جهة المُحقِّق فقط، بلا تغيير شكل تصدير الواجهة):**
- قبول `"records"` في `load_records` (الأشكال السابقة تبقى)
- عند وجود `data_version`: مقارنة مع المضمَّن في `web/fahras.html`؛ اختلاف ⇒ رفض الكتابة + رسالة عربية ثابتة + خروج 2؛ `--allow-version-mismatch` اختياري غير افتراضي
- `import_reviews` يعيد استخدام `load_records` بلا نسخ
- اختبارات ملفّقة (tmp) للتطابق / الاختلاف / المصفوفة الفارغة (خروج 0)

---

## ١١. PART 5 — حارس مسارات التجميد في CI

Pathspecs كانت `data/**/raw` فتطابق صفراً من الملفات؛ صارت `:(glob)data/**/{raw,layers,spans,windows}/**` مع `--diff-filter=MDR` (تعديل/حذف/إعادة تسمية مرفوض؛ إضافة ملفات جديدة مسموحة) + فحص نظافة ما بعد البناء منفصل.
