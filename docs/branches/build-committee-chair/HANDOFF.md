# تسليم فرع رئيس اللجنة — build/committee-chair

## ١. ماذا تغيّر ولماذا
بناء رئيس لجنة تحكيم حتمي (`src/committee_chair.py`) يركب على مخرجات الفاحص الحتمي لوكيلين من عائلتين مختلفتين.
الهدف: رفع عتبة التوافق إلى ٨٥ وفرض خمسة شروط صارمة للترشيح وتوحيد رموز الامتناع المغلقة قبل مراجعة المتخصص البشري.

## ٢. الملفات المتغيرة والجديدة
- `src/committee_chair.py`: محرك التحكيم الحتمي، وفحص استقلال العائلتين والبصمات، وتوليد ملفات القرارات.
- `src/grounding_contract.py`: ثوابت اللجنة (`COMMITTEE_THRESHOLD = 85`، رموز الامتناع المغلقة، شعار «أعداد توجيه وليست دقة»).
- `tests/test_committee_chair.py`: ٢٠ اختباراً شاملاً للقواعد السلبية والحالات الإيجابية والمسار الكامل طرفاً لطرف.

## ٣. بنية التحكيم: الطبقتان وشروط الترشيح ورموز الامتناع
- **الطبقتان**: الفاحص الحتمي (`v2_verify.py`) بعتبة ٧٥ لكل وكيل ← رئيس اللجنة (`committee_chair.py`) بعتبة ٨٥ للتوافق.
- **شروط الترشيح الخمسة**: عائلتان مختلفتان وبصمة حزمة متطابقة، ثم: ١) كلا المسارين `auto_candidate`، ٢) تطابق `primary`، ٣) تداخل أجزاء حقيقي دون تكرار استخدام حركة المدقق، ٤) درجة المقترح ≥ ٨٥، ٥) خلو الطرفين من أعلام الدليل.
- **رموز الامتناع المغلقة (بالترتيب الأسبق)**:
  1. `written_abstain`: امتناع بسبب مكتوب (المنهج الرئيسي فارغ أو يقين غير كافٍ).
  2. `force_specialist`: إحالة الفاحص — تُحترم (مخرج الفاحص لأي طرف `specialist` أو خلل في بصمة الحزمة).
  3. `agent_disagree`: اختلاف الوكلاء في تعيين المنهج الرئيسي.
  4. `unclear_bounds`: حدود غير واضحة (انعدام تقاطع الأجزاء، عدم اتصال، أو إعادة استخدام حركة المدقق).
  5. `weak_evidence`: دليل ضعيف (يقين ضعيف، درجة المقترح دون ٨٥، أو أعلام دليل).
- **المخرجات المكتوبة**: يكتب `<base>/committee/<window>.json` و`<base>/verified/committee/<window>.json`؛ وتبقى ملفات الدخل في `verified/` متطابقة بالبايت دون أي تعديل.

## ٤. جدول إثبات القواعد بالاختبارات
| القاعدة | اسم الاختبار في `tests/test_committee_chair.py` |
|---|---|
| درجة المقترح دون ٨٥ ← دليل ضعيف | `test_both_auto_proposer_score_80_yields_weak_evidence` |
| اختلاف المنهج الرئيسي ← اختلاف الوكلاء | `test_different_primary_yields_agent_disagree` |
| إحالة المدقق لمتخصص في الفاحص ← إحالة الفاحص | `test_reviewer_specialist_yields_force_specialist_with_copied_code` |
| انعدام تقاطع الأجزاء ← حدود غير واضحة | `test_no_overlap_yields_unclear_bounds` |
| يقين غير كاف أو منهج فارغ ← امتناع مكتوب | `test_insufficient_certainty_or_empty_primary_yields_written_abstain` |
| تماثل عائلة النموذجين ← رفض التشغيل | `test_same_family_refused` |
| تباين أو غياب بصمة الحزمة ← إحالة الفاحص | `test_packet_hash_mismatch_and_missing_yields_force_specialist` |
| بقاء ملفات الدخل متطابقة بالبايت | `test_input_verified_files_remain_byte_identical` |
| حماية سلامة التشغيل عند تشوه البنية | `test_shape_validation_flags_missing_yields_specialist` |
| تضارب مدققين متعددين في المنهج | `test_multi_overlap_reviewer_split_disagreement_yields_agent_disagree` |
| منع تكرار حركة المدقق لأكثر من مقترح | `test_reused_reviewer_move_forces_unclear_bounds` |
| الحركات الزائدة للمدقق تخرج لمتخصص | `test_unmatched_reviewer_move_emitted_as_specialist_in_both_files` |
| استيفاء شروط الترشيح ← مرشح للقبول | `test_positive_both_auto_overlap_score_90_no_flags` |
| مسار كامل طرفاً لطرف (تصنيف-فاحص-لجنة) | `test_full_chain_grounded_and_ungrounded` |

## ٥. طريقة الاستخدام (أوامر حقيقية من سورة النور)
تشغيل نافذة محددة:
```bash
python src/committee_chair.py --base data/nur/al_tabari --proposer qwen2.5-14b-local --reviewer gemma2-9b-local --window 24_35_p01
```
تشغيل كافة النوافذ الجاهزة دفعة واحدة:
```bash
python src/committee_chair.py --base data/nur/al_tabari --proposer qwen2.5-14b-local --reviewer gemma2-9b-local --all
```

## ٦. كيف تتحقق بنفسك
تشغيل حزمة الاختبارات الشاملة للفرع:
```bash
python -m unittest tests/test_committee_chair.py
```
الناتج المتوقع:
`Ran 20 tests in 0.153s - OK`

## ٧. ما لا يفعله هذا الفرع والحدود
- لا استدعاء لنماذج لغوية؛ القرار حتمي حسابي خالص (خُطّاف الصياغة يُرجع النص الثابت المحدد).
- ليس اعتماداً نهائياً؛ صفة «مرشح للقبول» آلية مبدئية، وكلمة «اعتماد» محجوزة للمتخصص البشري وحده.
- لم ندرّب نماذج؛ والعد إرشادي («أعداد توجيه وليست دقة»).

## ٨. سجل التنفيذ والمراجعة المستقلة
- **المنفّذ**: Antigravity (Gemini 3.8 Flash High).
- **المراجعة المستقلة**: Codex عبر ٣ جولات تدقيق (إصلاح ٤ ملاحظات P1، وإصلاح انحدار P1) — النتيجة: PASS.
- **برهان الفشل والسبق (fail-before)**: Claude.
