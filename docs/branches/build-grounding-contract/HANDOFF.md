# تسليم فرع عقد الإسناد — المرحلة صفر

## ماذا تغيّر ولماذا
أغلقنا الفجوات السبع في مسار الوسم قبل أي تشغيل جماعي: لا شاهد بديل مولّد، وبوابة كفاية دليل حتمية، ورموز امتناع مغلقة، وربط كل رد ببصمة حزمته.
قاعدة المسابقة المطبقة: سؤال ← استرجاع ← هل الدليل كافٍ؟ ← نعم: صياغة مسندة / لا: امتناع أو إحالة.

## الملفات المتغيرة
- <bdi dir="ltr">src/grounding_contract.py</bdi> — جديد: قائمة رموز مغلقة ودوال البصمة
- <bdi dir="ltr">src/v2_verify.py</bdi> — بوابة الكفاية وربط البصمة
- <bdi dir="ltr">src/classify_api.py</bdi> — بصمة الطلب وسجلات الفشل
- <bdi dir="ltr">src/run_window.py</bdi> — اليدوي غير مضمون أبداً
- <bdi dir="ltr">src/v2_selftest.py</bdi> — تغطية المسارات الجديدة
- <bdi dir="ltr">tests/test_grounding_verifier.py</bdi> و<bdi dir="ltr">tests/test_grounding_io.py</bdi> — جديدان (٢٥ اختباراً)

## الفجوات ٠-١..٠-٧ والدليل

| الفجوة | ما كان خطأ | ما يفعله الكود الآن | اختبار الإثبات |
|---|---|---|---|
| ٠-١ | الشاهد الفارغ يُستبدل بأجزاء الحركة | لا بديل مولّد؛ فارغ = متخصص | <bdi dir="ltr">test_empty_evidence_no_substitution</bdi> |
| ٠-٢ | شاهد الحكم يُحتسب من أي موضع | قيد قرب صريح من الحركة | <bdi dir="ltr">test_verdict_far_from_move</bdi> |
| ٠-٣ | حقول حرة تُعرض بلا إسناد | كل ادعاء مربوط بشاهد أو يُعزل | <bdi dir="ltr">test_ungrounded_hadith_reference</bdi> |
| ٠-٤ | لا بوابة كفاية مستقلة | شاهد صريح + علامة مناسبة + حدود سليمة | <bdi dir="ltr">test_editor_only_evidence_despite_high_certainty</bdi> |
| ٠-٥ | لا رموز امتناع مغلقة | كل رفض = رمز واحد من قائمة مغلقة | <bdi dir="ltr">test_specialist_reasons_are_closed_and_auto_is_none</bdi> |
| ٠-٦ | اليدوي يسمح بسياق خارج الحزمة | اليدوي موسوم غير مضمون ولا يُرشَّح أبداً | <bdi dir="ltr">test_manual_in_saves_unverified_assurance_and_no_valid_hash</bdi> |
| ٠-٧ | الفاحص غير مربوط بالبصمة | بصمة مسجلة ومطابَقة في الطلب والمخرج | <bdi dir="ltr">test_packet_byte_change_mismatches</bdi> |

## طريقة الاستخدام (مشغّل النماذج)
١. افحص الحزمة أولاً دون شبكة:
<bdi dir="ltr"><code>python src/run_window.py --tafsir al_tabari --window 24_35_p01 --base data/nur/al_tabari --dry-run</code></bdi>
٢. التشغيل عبر الواجهة (المفتاح في متغير الجلسة فقط):
<bdi dir="ltr"><code>python src/run_window.py --tafsir al_tabari --window 24_35_p01 --base data/nur/al_tabari --api --model qwen2.5:32b --base-url http://localhost:11434/v1</code></bdi>
٣. سجل الفشل شكله ثابت (لا ملف حركات يُكتب):
<bdi dir="ltr"><code>{"window_id": "24_35_p01", "status": "failed", "reason_code": "RUN_FAILURE", "error": "..."}</code></bdi>
٤. رمز السبب في المخرج بعد الفحص (verified): حقل واحد من القائمة المغلقة؛ المرشح الآلي رمزه فارغ، والمحال للمتخصص يحمل رمزاً واحداً.
٥. اليدوي غير مرشَّح أبداً: <bdi dir="ltr"><code>--manual-out</code></bdi> يكتب ملف لصق، و<bdi dir="ltr"><code>--manual-in</code></bdi> يحفظ الرد موسوماً غير مضمون — لا يُرشَّح أبداً.

## كيف تتحقق بنفسك
- <bdi dir="ltr"><code>python -m pytest tests/test_grounding_verifier.py tests/test_grounding_io.py -q</code></bdi> ← ‏٢٥ نجاحاً
- <bdi dir="ltr"><code>python src/v2_selftest.py</code></bdi> ← ‏يطبع نجاح الفحص الذاتي
- <bdi dir="ltr"><code>git status --porcelain</code></bdi> ← ‏لا شيء تحت بيانات المصدر

## ما لم يُنجَز / مخاطر
لم ندرّب أي نموذج؛ الأرقام أعداد توجيه وليست دقة. الاعتماد للمتخصص البشري فقط. وكيلان من عائلتين مختلفتين مطلوبان قبل الجماعي.

## من نفّذ ومن راجع
العقد: كلود (منسّق)؛ الفاحص: كرسور؛ المنتِج: أنتيغرافيتي؛ مراجعات مستقلة: كودكس (٤ مراجعات، كل الملاحظات مُصلحة)؛ إثبات الفشل على الأساس: كلود.
