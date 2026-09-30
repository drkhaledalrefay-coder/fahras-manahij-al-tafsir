# مراجعة classify_api

**الحكم: سليم للدمج**

فحص تشغيلي للملفات الأربعة (ليس قراءة فقط).

1. **أمن.** المفتاح من `LLM_API_KEY` فقط — لا `--api-key`. `classify_api.py` بلا `print`/`logging`. `--dry-run` مع `LEAK_TEST_KEY_xyz_never` لم يظهر في الخرج؛ ملفات moves/verified الناتجة خالية منه. `web/` لم يُمس (`git status -- web/` فارغ). `test_api_key_never_logged` نجح.

2. **دورة يدوية.** `--manual-out` كتب الـ prompt. `--manual-in data/multi/al_tabari/moves/deepseek/2_102.json` طبع `verifier: moves=6 auto=1 specialist=5 flags=5` = ملخص Run 2 في `verified/deepseek/2_102.json`.

3. **رد باطل.** `--manual-in` بـ `s_NOT_IN_PACKET` خرج 1: `invalid span ids` / `unknown span id 's_NOT_IN_PACKET' in move[0].span_ids`.

4. **الشكل.** مفاتيح `window`/`moves` + 11 حقل حركة + `references.{verses,hadith,persons}` مطابقة للأصل؛ الكائنان متساويان.

5. **شبكة/اختبارات.** `--dry-run` و`--api --dry-run` مع `urlopen` معطّل → خروج 0. pytest: `tests/test_classify_api.py` 8/8؛ `tests/test_export_approved.py` 22/22.

6. **التوثيق.** أوامر `docs/AI_RUN.md` والمتغيرات `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` تطابق الكود؛ `python src/build_fahras.py` موجود بلا وسائط.

عيوب حاجبة: لا شيء.
