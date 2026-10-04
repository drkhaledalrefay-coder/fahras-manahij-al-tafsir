# دفتر التشغيل — فهرسة مناهج التفسير (Ollama على جهاز المعالج الرسومي)

كل علَم هنا من `--help` الفعلي. الأوامر بصيغة PowerShell (ويندوز).

## ٠. الأعلام

| السكربت | الأعلام |
|---|---|
| `src/run_window.py` | `--tafsir` · `--base` · `--window` · `--api` \| `--manual-out FILE` \| `--manual-in FILE` · `--dry-run` · `--model` · `--base-url` |
| `src/v2_verify.py` | `--base` |
| `src/committee_chair.py` | `--base` · `--proposer` · `--reviewer` · `--window` \| `--all` · `--proposer-tag` · `--reviewer-tag` · `--proposer-quant` · `--reviewer-quant` |
| `src/run_surah.py` | `--db` (إلزامي) · `--tafsir` · `--surah` (الافتراضي **8**) · `--ayat` · `--base` · `--dry-run` · `--classify` · `--time-cap` |

## ١. التحقق والفرع

```powershell
git status                          # يجب أن تكون شجرة العمل نظيفة؛ وإلا توقّف واسأل المشغّل
git fetch origin
git switch -c tagging/nur-<tafsir>-<operator>-<YYYYMMDD> origin/main   # اسم فريد لكل تشغيل، لا عمل على main
pip install -r requirements.txt
pip install pytest                  # ليست في requirements.txt؛ CI يثبّتها بالطريقة نفسها
python -m pytest -q
python src/v2_selftest.py           # يجب: SELFTEST PASS
```

## ٢. جلسة الطرفية (لا تُحفظ في ملف)

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:LLM_API_KEY = "ollama"
$env:LLM_BASE_URL = "http://localhost:11434/v1"
```

## ٣. النماذج — عائلتان مختلفتان

| ذاكرة المعالج | المصنّف (المقترِح) | المدقّق (المراجِع) |
|---|---|---|
| ٤٨ غيغابايت فأكثر | `qwen2.5:72b` | `llama3.3:70b` أو `gemma3:27b` |
| **٢٤ غيغابايت (الافتراضي)** | `qwen2.5:32b` | `gemma3:27b` |
| ١٦ غيغابايت | `qwen2.5:14b` | `gemma3:12b` |

```powershell
ollama pull qwen2.5:32b
ollama pull gemma3:27b
ollama list                          # سجّل الوسم الفعلي كما يظهر هنا
```

اسم مجلد الوكيل يُشتق من اسم النموذج (`model_slug`): `qwen2.5:32b` ← `qwen2_5_32b`، و`gemma3:27b` ← `gemma3_27b`. هذا الاسم هو ما يُمرَّر للرئيس.

## ٤. العيّنة ٢٤:٣٥ — ثم توقّف

| التفسير | `--base` | النوافذ |
|---|---|---|
| الطبري | `data/nur/al_tabari` | `24_35_p01` `24_35_p02` `24_35_p03` `24_35_p04` |
| ابن كثير | `data/nur/ibn_kathir` | `24_35_p01` `24_35_p02` `24_35_p03` |
| البغوي | `data/nur/al_baghawi` | `24_35` |
| السعدي | `data/nur/al_saadi` | `24_35` |

```powershell
# فحص بلا شبكة: يطبع packet_sha256 وعدد الأجزاء
python src/run_window.py --tafsir al_tabari --base data/nur/al_tabari --window 24_35_p01 --dry-run

# الوكيلان على النافذة نفسها (كل تشغيل يكتب moves/<slug>/ و verified/<slug>/ تلقائياً)
python src/run_window.py --tafsir al_tabari --base data/nur/al_tabari --window 24_35_p01 --api --model qwen2.5:32b
python src/run_window.py --tafsir al_tabari --base data/nur/al_tabari --window 24_35_p01 --api --model gemma3:27b

# رئيس اللجنة على النافذة
python src/committee_chair.py --base data/nur/al_tabari --proposer qwen2_5_32b --reviewer gemma3_27b --window 24_35_p01 --proposer-tag qwen2.5:32b --reviewer-tag gemma3:27b
```

كرّر لكل صف في الجدول. **توقّف هنا** وسلّم للمراجعة: عيّنة عمياء ومراجعة عدائية، ثم المراجعة الشرعية.

**نجاح التشغيل:** سطر `verifier: moves=… auto=… specialist=…`، وملفات `verified/<slug>/<window>.json` و`committee/<window>.json` و`verified/committee/<window>.json`.
**فشل التشغيل:** سطر JSON فيه `"status": "failed"` و`reason_code` (`RUN_FAILURE` أو `MODEL_OUTPUT_INVALID`)، وخروج بغير صفر، ولا ملف حركات. هذا سلوك مقصود.

## ٥. الجماعي — بعد قبول العيّنة فقط

الطريق الموصى به: حلقة على نوافذ التفسير. لا تحتاج `quran.db`.

```powershell
$t = "al_tabari"; $base = "data/nur/$t"
foreach ($m in "qwen2.5:32b", "gemma3:27b") {
  Get-ChildItem "$base/packets/*.json" | ForEach-Object {
    python src/run_window.py --tafsir $t --base $base --window $_.BaseName --api --model $m
  }
}
python src/committee_chair.py --base $base --proposer qwen2_5_32b --reviewer gemma3_27b --all --proposer-tag qwen2.5:32b --reviewer-tag gemma3:27b
```

كرّر مع `$t` = `ibn_kathir` ثم `al_baghawi` ثم `al_saadi`.

بديل `run_surah.py`: يحتاج `--db` إلى `quran.db` بالبصمة الموثّقة في `docs/TAGGING_PLAN_NUR.md`، ويأخذ النموذج من `$env:LLM_MODEL` لا من علَم. **مرّر `--surah 24` صراحة** لأن الافتراضي ٨.

```powershell
$env:LLM_MODEL = "qwen2.5:32b"
python src/run_surah.py --db "<path>/quran.db" --tafsir al_tabari --surah 24 --base data/nur/al_tabari --classify --time-cap 300
```

السياق: أطول نوافذ النور طويلة؛ إن تكرر `MODEL_OUTPUT_INVALID` فارفع `num_ctx` في Ollama (مثلاً ١٦٣٨٤).

## ٦. التسجيل

```powershell
git add data/nur/al_tabari/moves data/nur/al_tabari/verified data/nur/al_tabari/committee
git commit -m "data(nur): al_tabari tagged — qwen2.5:32b + gemma3:27b (ollama-local) 2026-10-05"
git push -u origin HEAD              # يدفع فرعك أنت، لا main
```

ثم PR ← CI أخضر ← مراجعة. **لا push على `main`.** لا تُرفع `quran.db` أبداً.
