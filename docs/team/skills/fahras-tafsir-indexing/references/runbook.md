# دفتر التشغيل (Runbook) — مشغّل الذكاء على صندوق GPU مع Ollama

> المصادر: `docs/TAGGING_PLAN_NUR.md` §3-§4، `docs/HANDOFF.md` §4، ومخرجات `--help` الحقيقية أدناه.
> كل الأعلام هنا موجودة حرفياً في `--help` — لا تستخدم غيرها.

## 0. الأعلام الحقيقية (انسخها من `--help`)

**`python src/run_window.py --help`:**
`--tafsir` · `--base` · `--window` · `--api` · `--manual-out FILE` · `--manual-in FILE` · `--dry-run` · `--model MODEL` · `--base-url BASE_URL`

**`python src/run_surah.py --help`:**
`--db DB` · `--tafsir {al_tabari,al_saadi,al_baghawi,ibn_kathir}` · `--surah SURAH` · `--ayat AYAT` · `--base BASE` · `--dry-run` · `--classify` · `--time-cap TIME_CAP`

**`python src/v2_verify.py --help`:**
`--base BASE`

## 1. قبل التشغيل (المرحلة 0)

- لا وسم جماعي على النور قبل دمج المرحلة 0 واجتياز اختباراتها (`docs/TAGGING_PLAN_NUR.md` §2).
- بعد الدمج شغّل: `python -m pytest -q` (أمر الخطة §4 خطوة 1).

## 2. جلسة الطرفية (PowerShell على Windows — للجلسة فقط)

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:LLM_API_KEY = "ollama"
$env:LLM_BASE_URL = "http://localhost:11434/v1"
```

- المفتاح في متغير بيئة الجلسة فقط — لا ملف ولا git ولا شات (`docs/TAGGING_PLAN_NUR.md` §3).
- درجة الحرارة `temperature: 0` للمصنّف والمدقّق وصياغة سبب الامتناع (تُضبط في طلب الـAPI، وليست علماً في CLI).

## 3. النماذج: اسحب وسجّل الوسم الفعلي

```powershell
ollama pull qwen2.5:32b
ollama pull gemma3:27b
ollama list
```

- التوصية الافتراضية لذاكرة 24GB: المصنّف `qwen2.5:32b` والمدقّق `gemma3:27b` (`docs/TAGGING_PLAN_NUR.md` §3).
- البدائل حسب الذاكرة: 48GB ← `qwen2.5:72b` + (`llama3.3:70b` أو `gemma3:27b`)؛ 16GB ← `qwen2.5:14b` + `gemma3:12b`.
- سجّل **الوسم الفعلي** من `ollama list` في `committee.json` وفي العرض — لا تذكر اسماً لم يُشغَّل فعلاً.

## 4. العيّنة أولاً: آية النور 24:35 على التفاسير الأربعة ثم توقّف

معرّفات النوافذ الحقيقية (من `data/nur/<tafsir>/windows/`):

| التفسير | `--base` | `--window` |
|---|---|---|
| الطبري | `data/nur/al_tabari` | `24_35_p01` `24_35_p02` `24_35_p03` `24_35_p04` |
| ابن كثير | `data/nur/ibn_kathir` | `24_35_p01` `24_35_p02` `24_35_p03` |
| البغوي | `data/nur/al_baghawi` | `24_35` |
| السعدي | `data/nur/al_saadi` | `24_35` |

```powershell
python src/run_window.py --tafsir al_tabari --window 24_35_p01 --base data/nur/al_tabari --dry-run
python src/run_window.py --tafsir al_tabari --window 24_35_p01 --base data/nur/al_tabari --api --model qwen2.5:32b
```

- كرر لكل نافذة عيّنة في الجدول (نفس النمط مع `--tafsir` و`--base` و`--window` المناسبة).
- بلا مفتاح (احتياطي يدوي من `docs/HANDOFF.md` §4):
  `python src/run_window.py --base data/nur/al_tabari --window 24_35_p01 --dry-run`
  ثم `--manual-out prompt.txt` وبعد اللصق `--manual-in reply.json` (الناتج `manual_unverified` — لا يُرشَّح أبداً).
- **توقّف بعد العيّنة** لمراجعة القسم 5 من الخطة قبل أي تشغيل جماعي.

## 5. التشغيل الجماعي (بعد قبول العيّنة فقط)

```powershell
python src/run_surah.py --db "<path>/quran.db" --tafsir al_tabari --surah 24 --base data/nur/al_tabari --classify --time-cap 300
```

- كرر لكل تفسير (`al_tabari`، `ibn_kathir`، `al_baghawi`، `al_saadi`) مع `--base` المطابق.
- ثم شغّل المدقّق من العائلة الثانية على نفس الحزم (مثال `--model gemma3:27b`)، ثم الفاحص الحتمي:
  `python src/v2_verify.py --base data/nur/al_tabari`
- قاعدة `--ayat`: الصيغ المقبولة `1-20` أو `2,3,4` أو رقم واحد (من `src/run_surah.py`).

## 6. التسجيل والفرع

- **commit واحد لكل تفسير** بعد اجتياز البوابات، والرسالة فيها اسم النموذج الفعلي وتاريخ التشغيل.
- العمل على فرعك ثم PR — **ممنوع الدفع إلى `main`** (`AGENTS.md` القاعدة 8).
- لا تلمس `data/**/{raw,layers,spans,windows}` ولا `web/*.html` يدوياً ولا `quran.db` (لا يُرفع أبداً).
