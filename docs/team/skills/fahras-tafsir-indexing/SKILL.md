---
name: fahras-tafsir-indexing
description: فهرسة مناهج التفسير — run the project's two-agent indexing pipeline on the fixed tafsir text (classifier + reviewer from two model families via Ollama, deterministic verifier at 75, committee chair at 85) and prepare results for the human specialist. Use when tagging tafsir methods on a window or a surah (the 24:35 sample, mass tagging of Surah An-Nur), when running run_window.py / v2_verify.py / committee_chair.py, or when reading reason codes in verified/ and committee/ outputs. Never use it to interpret verses or approve anything.
---

# فهرسة مناهج التفسير

المنتج **يفهرس المنهج** (أثر، حديث، لغة، رأي…) على نص مصدر مثبّت حرفاً بحرف. **لا يفسّر ولا يفتي ولا يعتمد.** النموذج يقترح بمعرّفات الأجزاء فقط؛ الكود يفحص؛ المتخصص البشري وحده يعتمد.

التفاصيل: [`references/runbook.md`](references/runbook.md) (الأوامر) · [`references/reason-codes.md`](references/reason-codes.md) (الرموز) · [`references/methods.md`](references/methods.md) (المناهج واليقين).

## السلسلة — طبقتان حتميتان فوق وكيلين

```
نافذة مثبّتة → حزمة + بصمة → وكيل ١ (عائلة Qwen)  ┐
                              → وكيل ٢ (عائلة أخرى) ┘ → الفاحص لكل وكيل → رئيس اللجنة → المتخصص
```

| الطبقة | الكود | يرشّح «مرشّح للمراجعة» فقط إذا | وإلا |
|---|---|---|---|
| ١ الفاحص (لكل وكيل) | `src/v2_verify.py` | شاهد صريح داخل الحركة، بوابة الكفاية، بصمة الحزمة مطابقة، مدخل `api_packet`، يقين `explicit/strong`، درجة ≥ **٧٥**، بلا أعلام | `specialist` + **رمز واحد** من `REASON_CODES` |
| ٢ رئيس اللجنة | `src/committee_chair.py` | الوكيلان مرشّحان + نفس المنهج + تداخل أجزاء حقيقي + درجة المصنّف ≥ **٨٥** + بلا أعلام + عائلتان مختلفتان + بصمتان متطابقتان | `specialist` + **رمز واحد** من `COMMITTEE_REASON_CODES` |

٧٥ و٨٥ **ليستا تعارضاً**: ٧٥ حدّ الوكيل الواحد، و٨٥ حدّ اتفاق اللجنة. ولا واحدة منهما اعتماد.

## الإجراء

1. **تحقّق قبل أي شيء:** شجرة عمل نظيفة، ثم فرع فريد من `origin/main` (`tagging/nur-<tafsir>-<operator>-<YYYYMMDD>`)، ثم `pip install pytest` و`python -m pytest -q` و`python src/v2_selftest.py` ← PASS. لا عمل على `main`.
2. **جلسة الطرفية فقط:** `LLM_API_KEY=ollama` و`LLM_BASE_URL=http://localhost:11434/v1` و`PYTHONIOENCODING=utf-8`. لا مفتاح في ملف ولا git ولا محادثة.
3. **النماذج:** `ollama pull` لعائلتين مختلفتين، ثم `ollama list` وسجّل **الوسم الفعلي**. اسم مجلد الوكيل = `model_slug(model)`: `qwen2.5:32b` ← `qwen2_5_32b`.
4. **`--dry-run` أولاً** لكل نافذة جديدة: يجب أن يطبع `packet_sha256` وعدد الأجزاء دون شبكة.
5. **العيّنة ٢٤:٣٥** على التفاسير الأربعة بالوكيلين، ثم الرئيس، ثم **توقّف**. لا تشغيل جماعي قبل مراجعة العيّنة (خطة الوسم §٥).
6. **الجماعي** بعد قبول العيّنة: حلقة على نوافذ كل تفسير لكل وكيل، ثم `committee_chair.py --all`.
7. **التسجيل:** commit لكل تفسير؛ الرسالة تذكر الوسمين الفعليين والتاريخ؛ فرع ← PR ← CI أخضر ← مراجعة.

الأوامر الحرفية لكل خطوة في [`references/runbook.md`](references/runbook.md).

## قواعد لا تُكسر

- لا تعديل على `data/**/{raw,layers,spans,windows}` ولا إعادة كتابة للنص (CI يحرسها).
- لا اعتماد آلي. «اعتماد» كلمة المتخصص وحده. «مرشّح للمراجعة» ليس اعتماداً.
- الرد اليدوي (`--manual-in`) = `manual_unverified` **لا يُرشَّح أبداً**؛ لا تستعمله لتسريع التشغيل.
- وكيلان من **عائلتين**؛ نموذجان من العائلة نفسها (مثل `qwen2.5:32b` و`qwen2.5:14b`) يرفضهما الرئيس.
- الأرقام «**أعداد توجيه وليست دقة**»: لا نسب، لا ادعاء دقة، لا «الأول». «لم ندرّب»، «وكيلان».
- لا تذكر نموذجاً لم يظهر في `ollama list` ولم يُشغَّل فعلاً. «محلي» فقط إن كان `LLM_BASE_URL` على localhost.

## توقّف وصعّد إذا

- **كل الحركات اتفاق** أو كلها `auto_candidate` ← علامة شك لا نجاح.
- `PACKET_HASH_MISMATCH` ← الحزمة تغيّرت؛ لا تُصلح بالتحايل، أعد التشغيل.
- تكرار `RUN_FAILURE` أو `MODEL_OUTPUT_INVALID` ← ارفع `num_ctx` أو صغّر النموذج، ولا تعدّل الفاحص.
- رفض الرئيس لـ«عائلة واحدة» ← اختر نموذجاً من عائلة أخرى.
- أي رغبة في خفض ٧٥ أو ٨٥ أو تعطيل بوابة ← **ممنوع**؛ القرار لقائد الفريق.
