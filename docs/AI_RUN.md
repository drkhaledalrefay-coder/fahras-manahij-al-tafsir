# تشغيل التصنيف بالذكاء الاصطناعي

دليل قصير لتشغيل مصنّف المنهجية على نافذة واحدة (API أو يدوي بلا مفتاح).

## القواعد

- **لا تضع مفتاح API في `web/` ولا في git.** المفتاح من متغيّر البيئة فقط: `LLM_API_KEY`.
- مخرجات النموذج = **«مقترح آلي»** حتى يوافق مختصّ التفسير. لا تُنشر كمعتمد.

## إعداد البيئة (وضع API)

```bash
# Windows PowerShell
$env:LLM_API_KEY = "..."
$env:LLM_BASE_URL = "https://api.openai.com/v1"   # أو أي نقطة OpenAI-compatible
$env:LLM_MODEL = "gpt-4o-mini"
```

```bash
# bash
export LLM_API_KEY=...
export LLM_BASE_URL=https://api.openai.com/v1
export LLM_MODEL=gpt-4o-mini
```

## وضع API

```bash
python src/run_window.py --tafsir al_tabari --window 2_102 --api
# أو مع تجاوز النموذج:
python src/run_window.py --tafsir al_tabari --window 2_102 --api --model deepseek-chat
```

يكتب الملف تحت `data/multi/<tafsir>/moves/<model_slug>/<window>.json` ثم يشغّل المتحقّق الصارم.

تجربة بلا شبكة:

```bash
python src/run_window.py --tafsir al_tabari --window 2_102 --dry-run
```

## وضع يدوي (بدون API)

1. اكتب ملف التعليمات:

```bash
python src/run_window.py --tafsir al_tabari --window 2_102 --manual-out prompt.txt
```

2. الصق محتوى `prompt.txt` في ChatGPT / Claude / Gemini، واطلب JSON فقط.
3. احفظ الرد في ملف (مثلاً `reply.json`) ثم:

```bash
python src/run_window.py --tafsir al_tabari --window 2_102 --manual-in reply.json
```

يُحفظ تحت `moves/manual_YYYY-MM-DD/<window>.json` ثم يُشغَّل المتحقّق.

## ماذا يعني خرج المتحقّق؟

سطر مثل: `verifier: moves=6 auto=2 specialist=4 flags=3`

| الحقل | المعنى |
|---|---|
| **moves** | عدد الحركات المقترحة |
| **auto** | مرشّح آلي (`auto_candidate`) — قد يُراجع دفعةً لاحقاً |
| **specialist** | يحتاج قرار مختص |
| **flags** | مجموع أعلام القواعد/البنية على الحركات |

كل ذلك ما زال **مقترحاً آلياً** حتى الاعتماد البشري.

## إعادة بناء الموقع

بعد حفظ moves / verified:

```bash
python src/build_fahras.py
```

التفاسير المدعومة: `al_tabari` · `al_baghawi` · `al_saadi` · `ibn_kathir` (أساس `data/v2`).
