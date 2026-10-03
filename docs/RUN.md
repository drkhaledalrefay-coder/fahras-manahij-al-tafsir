# التشغيل وإعادة البناء — Runbook

الأوامر بالترتيب لإعادة بناء **كل شيء** في هذا المستودع. تُنفَّذ جميعها من **جذر المستودع**، وببايثون 3.11+. مسار المعالجة الأساسي يعتمد على المكتبة القياسية، وتلزم حزمة `jsonschema` لتصدير السجلات المعتمدة واختباراتها (`pip install jsonschema`).

لا مسارات شخصية في أي أمر: المصدر يُمرَّر بالوسائط، وكل مسار نسبي إلى جذر المستودع.

---

## ٠. تحضير `quran.db` (مصدر البيانات)

- الملف `quran.db` (SQLite، نحو ٢٣٤ م.ب) **غير مرفوع** في المستودع. يُنزَّل من مجموعة بيانات مركز تفسير للدراسات القرآنية المفتوحة على Hugging Face:
  <https://huggingface.co/datasets/tafsircenter/tafsir-mcp-data> (الملف `quran.db` في جذر المجموعة).
- يُمرَّر إلى سكربت الاستخراج بوسيلة `--db <path/to/quran.db>`؛ **لا يُكتب أي مسار داخل الكود**.
- يفتحه السكربت **قراءة فقط** (`mode=ro`)، ويتحقق قبل القراءة من بصمة الملف، وهي موثّقة في `data/raw/manifest.json`:

```text
sha256 = 10e61f615ab5e6a3440e8ecc8ba1dc2273d12cd9048752760fe53a44d191cc27
```

- نصوص ابن كثير الثلاثة مثبّتة مسبقاً في `data/raw/tafsircenter/`؛ ولتنزيل المصدر نفسه وتحديثه: `python src/fetch.py` (بلا وسائط/أعلام — no flags؛ يتطلب اتصالاً بالشبكة؛ ينزّل نحو ٢٣٤ م.ب لملف `quran.db` إلى المسار المتجاهل في git `data/raw/tafsircenter/quran.db` ونصوص quran.com إلى `data/raw/quran_com/`، ويوثّق البصمات في `data/raw/manifest.json`). نص المصدر الثاني (quran.com) غير مرفوع في المستودع، وسكربت `run_all.py` يُعيد تنزيله آلياً عبر الشبكة ما لم يكن مجلد `data/raw/quran_com/` موجوداً محلياً.

## ١. استخراج نصوص التفاسير الثلاثة

```bash
python src/multi_fetch.py --db "<path-to>/quran.db"
```

يقرأ ٩ نصوص (الطبري / السعدي / البغوي × الآيات 2:255 و 2:102 و 17:105) من الجداول `tafsir_tabary` و `tafsir_saadi` و `tafsir_baghawy`، ويكتبها كما هي في `data/raw/tafsircenter/<tafsir_id>/`، ويُثبّت لكل ملف قيداً في `data/raw/manifest.json`. حتمي ومتكرر التشغيل: يتخطّى الملف المطابق بالبصمة، ويتوقف إن وجد ملفاً ببصمة مختلفة.

## ٢. الطبقات ← الأجزاء ← النوافذ

```bash
# التفاسير الثلاثة (الطبري / السعدي / البغوي)
python src/multi_layers.py
python src/multi_spans.py
python src/multi_windows.py

# ابن كثير (يتطلب مخرجات run_all.py: data/layers و data/spans_author و data/spans_pilot)
python src/v2_windows.py
```

| الأمر | ما يفعله | المخرج |
|---|---|---|
| `multi_layers` | يفصل كلام المفسّر عن تنسيق الصفحة وحاشية المحقّق | `data/multi/<tafsir>/layers/<s>_<a>.json` |
| `multi_spans` | يقطّع كلام المفسّر إلى أجزاء (span) بمواضع حصرية | `data/multi/<tafsir>/spans/<s>_<a>.json` |
| `multi_windows` | يبني نوافذ التحليل الثلاث لكل تفسير | `data/multi/<tafsir>/windows/<window>.json` |
| `v2_windows` | يبني نوافذ التحليل الثلاث لابن كثير | `data/v2/windows/<window>.json` |

نوافذ ابن كثير تُبنى بـ `python src/v2_windows.py` وتحتاج إلى `data/layers` و`data/spans_author` و`data/spans_pilot` التي ينتجها `python src/run_all.py` (حيث لا يستدعي `run_all.py` سكربت `v2_windows` تلقائياً، أو يُعتمد على النسخ المثبّتة في المستودع). الترتيب هنا: تشغيل `run_all.py` ثم `python src/v2_windows.py`، ثم الانتقال إلى الخطوة ٣.

## ٣. كشف العلامات وبناء حزم التصنيف (`--base`)

الأساس الافتراضي `--base data/v2` (ابن كثير). لكل تفسير آخر مرّر الأساس واسم المفسّر:

```bash
# ابن كثير (الأساس الافتراضي)
python src/v2_markers.py
python src/v2_packets.py

# الطبري
python src/v2_markers.py --base data/multi/al_tabari --tafsir-name الطبري
python src/v2_packets.py --base data/multi/al_tabari --tafsir-name الطبري

# السعدي
python src/v2_markers.py --base data/multi/al_saadi --tafsir-name السعدي
python src/v2_packets.py --base data/multi/al_saadi --tafsir-name السعدي

# البغوي
python src/v2_markers.py --base data/multi/al_baghawi --tafsir-name البغوي
python src/v2_packets.py --base data/multi/al_baghawi --tafsir-name البغوي
```

- `v2_markers`: كشف علامات المنهج لكل جزء → `<base>/markers/`.
- `v2_packets`: حزم التصنيف لكل نافذة → `<base>/packets/`، وعند الأساس الافتراضي يكتب أيضاً تعليمات المصنّف `method/classifier_prompt_v2.md`.

## ٤. التصنيف — أمر بايثون أو لصق يدوي

التصنيف خطوة **غير حتمية** (لغة نموذج)، خارج خط التحقق الحتمي. المخرجات المثبّتة في المستودع تكفي لإعادة البناء دون استدعاء نموذج جديد.

للتشغيل على نافذة واحدة (API أو يدوي بلا مفتاح):

```bash
python src/run_window.py --tafsir al_tabari --window 2_102 --dry-run
# ثم --api أو --manual-out / --manual-in
```

الدليل الكامل (متغيّرات الجلسة، الأوامر، وإعادة البناء): [`AI_RUN.md`](AI_RUN.md).

- **التعليمات:** `method/classifier_prompt_v2.md` (التعريفات وقواعد اليقين ومخطط المخرج).
- **التعليم (briefs):** `method/agent-briefs/brief_v2_classify.txt` لابن كثير (Codex)، و`method/agent-briefs/brief_multi_B2_classify.txt` للتفاسير الثلاثة (DeepSeek)، و`method/agent-briefs/brief_multi_B2_al_tabari_2_255_mimo.txt` لنافذة الطبري 2:255 (MiMo).
- **المدخل:** `<base>/packets/<window>.json`.
- **المخرج:** `<base>/moves/<annotator>/<window>.json` — يشير المصنّف إلى النص **بمعرّفات الأجزاء (span IDs) فقط**، ولا ينسخ ولا يعيد صياغة حرفاً من المصدر.
- **القيود المفروضة على النموذج:** لا حركة بلا `evidence_span_ids`، ويتوقف (`insufficient`) عند غياب الدليل، وتصنيف الوظيفة لا الألفاظ، وكلام المحقّق ليس كلام المفسّر.
- من أُنجزت بها البيانات: **Codex** (OpenAI، النموذج `gpt-6-sol`) على ابن كثير، و**DeepSeek V4.1 Flash** (عبر Cline) على الأربعة، و**MiMo V2.6 Flash** (عبر Cline) على الطبري 2:255 — انظر [`AI_DISCLOSURE.md`](AI_DISCLOSURE.md).

```text
data/v2/moves/codex/                  ابن كثير — Codex
data/v2/moves/deepseek/               ابن كثير — DeepSeek
data/multi/al_tabari/moves/deepseek/  الطبري — DeepSeek
data/multi/al_tabari/moves/mimo/      الطبري 2:255 — MiMo
data/multi/al_saadi/moves/deepseek/   السعدي — DeepSeek
data/multi/al_baghawi/moves/deepseek/ البغوي — DeepSeek
```

## ٥. التحقق الحتمي والتوجيه

```bash
# ابن كثير → data/v2/verified/<annotator>/ و reports/v2_summary.md
python src/v2_verify.py

# الطبري + السعدي + البغوي دفعة واحدة → <base>/verified/<annotator>/ و <base>/summary.md
python src/multi_run_verify.py
```

أو لكل أساس على حدة:

```bash
python src/v2_verify.py --base data/multi/al_tabari
python src/v2_verify.py --base data/multi/al_saadi
python src/v2_verify.py --base data/multi/al_baghawi
```

المصنّف الآلي يُخرج معرّفات أجزاء فقط (span IDs) دون نص؛ ويعيد الفاحص الحتمي بناء نص كل حركة من مواضعها المعلنة ويطابقه حرفاً بحرف مع النص المثبّت، ويكتب النص المعاد بناؤه في المخرج (`text`)، ثم يمنح الحركة درجة ويوجّهها: **مرشّح آلي** أو **مختص**.

## ٦. بناء الصفحات

```bash
python src/build_fahras.py     # → web/fahras.html  (الصفحة الرئيسية، أربعة تفاسير)
python src/build_methods.py    # → web/methods.html (مرجع ابن كثير المجمَّد)
```

`build_fahras.py` حتمي البايتات عند ثبات البيانات: `embed(..., sort_keys=True)`، و`build_date` يُعاد استخدامه إن لم يتغيّر `data_version` (أو من `SOURCE_DATE_EPOCH`). الدوال المشتركة للقراءة/التجزئة/التبليط في `src/textcore.py`.

CI (GitHub Actions): `v2_selftest` + `pytest` + بناء مرتين مع `cmp`، ورفض أي تعديل تحت `raw|layers|spans|windows`.

### فتح الواجهة واستعراض النتائج

- **مباشرة في المتصفح:** افتح الملف `web/fahras.html` مباشرة دون الحاجة لأي خادم.
- **أو عبر خادم محلي:**
```bash
python -m http.server 8791 --directory web
```
ثم الانتقال في المتصفح إلى: `http://localhost:8791/fahras.html`

## ٧. تصدير الوسوم المعتمدة (سجلات المخطط الرسمي)

بعد اعتماد المتخصص للوسوم في واجهة المراجعة، يُستخدم سكربت التصدير لإنتاج سجلات معتمدة مطابقة لمخطط `schema/annotation.schema.json` ومتحققة حرفياً من النص المثبت:

```bash
python src/export_approved.py INPUT.json --out approved.json
```

- `INPUT.json`: مسار ملف JSON المنسوخ أو المحفوظ من زر «تصدير المعتمد» في واجهة المراجعة.
- `--out`: وسيلة **إلزامية** لتحديد مسار ملف الإخراج المعتمد `approved.json`.
- خيار اختياري: `--include-rejected` لتضمين الحركات المرفوضة أيضاً؛ أما الحركات غير المعتمدة (`ai_proposed` و `under_review`) فلا تُصدّر أبداً.
- يتطلب حزمة `jsonschema` (`pip install jsonschema`).

## ٨. الاختبارات

```bash
python src/v2_selftest.py
python -m unittest discover -s tests -p "test_*.py"
```

- يتطلب أمر `unittest` تثبيت حزمة `jsonschema` مسبقاً (`pip install jsonschema`)، لأن اختبار `tests/test_export_approved.py` يستورد `jsonschema` وسيُظهر خطأ استيراد `ImportError` في غيابها.
- `v2_selftest.py` يعمل بالمكتبة القياسية فقط ويتطلّب وجود نوافذ وعلامات ابن كثير (الخطوة ٣): يطبع `SELFTEST PASS` عند النجاح، ويرجع رمز خروج 1 عند الفشل.

---

## ملاحظات

- **مخرجات مثبّتة:** النصوص الخام والنوافذ والعلامات والحزم وحركات التصنيف كلها مرفوعة في المستودع؛ فلإعادة بناء الصفحات وحدها تكفي الخطوات ٥ ← ٦.
- **الترتيب الكامل:** ٠ → ١ → ٢ (تشمل تشغيل `run_all.py` ثم `python src/v2_windows.py` لابن كثير) → ٣ → ٤ (`src/run_window.py`) → ٥ → ٦ → ٧ → ٨. الخطوة ٥ لا تعمل بلا مخرجات ٤.
- **ترميز الطرفية (ويندوز):** إن أظهر أمرٌ ما `UnicodeEncodeError` عند طباعة نص عربي (كـ `--help` في `v2_markers` / `v2_packets`) فشغّله بوضع utf8: `python -X utf8 src/v2_markers.py …` أو عيّن `PYTHONIOENCODING=utf-8`. الترميز الافتراضي لبعض الطرفيات (cp1252) لا يحتمل الحروف العربية، والملفات نفسها سليمة.
- **صفحات التجربة الأولى وإعادة بناء نوافذ ابن كثير (اختيارية):**
  السكربت `python src/fetch.py` يعمل دون وسائط (no flags؛ يتطلب اتصالاً بالشبكة؛ ينزّل نحو ٢٣٤ م.ب لملف `quran.db` + نصوص quran.com). وسكربت `run_all.py` يعيد التنزيل عبر الشبكة إن لم يجد `data/raw/quran_com/` محلياً. بعد `run_all.py` يُشغّل `python src/v2_windows.py` لإنتاج نوافذ ابن كثير، ثم ننتقل إلى الخطوة ٣:

```bash
python src/fetch.py
python src/run_all.py
python src/v2_windows.py   # يبني data/v2/windows/ لابن كثير تمهيداً للخطوة ٣
python src/compare.py
python src/build_index.py
python src/build_reconcile.py
python src/build_app.py
```

---

## سورة الأنفال — أوامر أيام البناء

أوامر تشغيل خط استخراج وبناء وتصنيف سورة الأنفال كاملاً (٧٥ آية) عبر سكربت `src/run_surah.py` وسكربت `src/run_window.py` مع علم `--base`. يفتح السكربت قاعدة `quran.db` بوضع القراءة فقط (`mode=ro`)، ويتحقق من بصمة المصدر، والتشغيل حتمي ومتكرر (يتخطى النوافذ القائمة والمتحققة).

download quran.db once (see the section above for source + sha256), keep it OUTSIDE the repo, never commit it; tests read it from env QURAN_DB.

### ١. المعاينة والتحقق أولاً (Dry-Run First)

```bash
# معاينة استخراج سورة الأنفال دون استدعاء أي نموذج
python src/run_surah.py --db "<path-to>/quran.db" --tafsir al_tabari --surah 8 --base data/anfal/al_tabari --dry-run
```

### ٢. تشغيل نافذة واحدة (One Window)

```bash
# فحص الحزمة الجاهزة أولاً دون اتصال شبكي
python src/run_window.py --base data/anfal/al_tabari --window 8_2 --dry-run

# تصنيف النافذة بالذكاء الاصطناعي عبر API
python src/run_window.py --base data/anfal/al_tabari --window 8_2 --api
```

### ٣. تشغيل جميع نوافذ التفسير (All Windows)

```bash
# استخراج وبناء حزم جميع نوافذ الطبري لسورة الأنفال (٩٧ نافذة)
python src/run_surah.py --db "<path-to>/quran.db" --tafsir al_tabari --surah 8 --base data/anfal/al_tabari

# تشغيل حلقة التصنيف على جميع النوافذ مع حد زمني لكل نافذة وتوقف فوري عند HTTP 429
python src/run_surah.py --db "<path-to>/quran.db" --tafsir al_tabari --surah 8 --base data/anfal/al_tabari --classify
```

### ٤. التفاسير الأربعة لسورة الأنفال (Four Tafsirs)

```bash
# الطبري (97 نافذة)
python src/run_surah.py --db "<path-to>/quran.db" --tafsir al_tabari --surah 8 --base data/anfal/al_tabari

# ابن كثير (78 نافذة)
python src/run_surah.py --db "<path-to>/quran.db" --tafsir ibn_kathir --surah 8 --base data/anfal/ibn_kathir

# البغوي (75 نافذة)
python src/run_surah.py --db "<path-to>/quran.db" --tafsir al_baghawi --surah 8 --base data/anfal/al_baghawi

# السعدي (75 نافذة)
python src/run_surah.py --db "<path-to>/quran.db" --tafsir al_saadi --surah 8 --base data/anfal/al_saadi
```

---

## استيراد مراجعات الواجهة (`import_reviews`)

بعد «تصدير كل المعتمد» من الواجهة، يُستورد الملف بعد التحقق (مخطط + مطابقة المصدر المثبّت). التفاصيل: [`DECISIONS_PROPOSAL.md`](DECISIONS_PROPOSAL.md) و[`DATA_FORMAT.md`](DATA_FORMAT.md) «أداة التصدير».

شكل التصدير الكلاسيكي المقبول:

```json
{ "data_version": "<من البناء>", "records": [ /* سجلات معتمدة */ ] }
```

إن اختلف `data_version` عن المضمَّن في `web/fahras.html` يُرفض الاستيراد برسالة `نسخة البيانات مختلفة — أعد التحقق من القرارات` (خروج 2). `records: []` → لا ملفات، خروج 0.

```bash
# --out-root مطلوب دائماً. للاختبار: مجلد مؤقت. للاستيراد الحقيقي: جذر المستودع صراحةً.
python src/import_reviews.py export.json --base data/v2 --reviewer specialist_a --out-root .
# اختياري غير افتراضي: --allow-version-mismatch
```

لا يُكتب تحت `data/` إلا إذا مرّر المشغّل `--out-root` يؤول إلى هناك. الاختبارات تستخدم مجلداً مؤقتاً فقط.
