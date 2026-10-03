# صيغة بيانات الوسوم المعتمدة

**Tafsir Integrity — Annotation Data Format v1.0.0 (2026-09-28)**

هذه الصيغة تحفظ نتيجة العمل: **نصٌّ من تفسير مثبّت ببصمة، ووسومٌ راجعها إنسان**. يقرأها أي تطبيق قرآن، أو قاعدة بيانات، أو REST API، أو مجموعة بيانات بحثية، أو خادم MCP **دون ذكاء اصطناعي ودون واجهتنا**.
ابن كثير أول تفسير فقط؛ لا شيء في هذه الصيغة خاصٌّ به.

- المخطط: `schema/annotation.schema.json` — JSON Schema draft 2020-12.
- مثال معتمد حقيقي: `schema/example_approved.json` — من تفسير ابن كثير ٢:٢٥٥، المقطع `m20`.
- كل كائن في المخطط `additionalProperties: false`: أي حقل غير موثّق يُرفض السجل، حتى لا يتسلّل نصٌّ أو حقل غير معروف إلى البيانات المنشورة.

**سجل واحد أم مصفوفة؟** المخطط يصف **سجلاً واحداً**. التصدير العام = مصفوفة JSON من سجلات، يُحقَّق كل عنصر فيها بالمخطط. لا نُغيّر المخطط لكل مجموعة بيانات.

## 1) ثلاث طبقات لا تُخلط

| الطبقة | ما تحويه | من ينتجها | ما يُفعل بها |
|---|---|---|---|
| **نص المصدر المثبّت** | نصّ التفسير كما نُزّل (`data/raw/tafsircenter/...`)، ويمثّله `source.source_id` و `source.sha256` | التنزيل الآلي + البصمة | يُقرأ ولا يُعاد كتابته |
| **مقترح الآلة** | `ai_proposal`: حدود + وسوم + يقين + مؤشر + مسار | المصنّف الآلي | للتتبع والتدقيق، **ليس محتوى** |
| **الوسم المعتمد** | `labels` + `text` + `review.status = "approved"` | مختص تفسير بشري | هو المحتوى المنشور |

القاعدة الصارمة: **لا يُعاد النص في أي طبقة**. الطبقتان الثانية والثالثة لا تحملان نسخة نصية مستقلة، بل **أرقام مواضع** في المصدر. النموذج اللغوي لا يكتب ولا يصحّح ولا يلخّص؛ يقترح حدوداً ووسوماً فقط، والمتخصص يعتمد — لذلك يبقى الفرق بين `ai_proposal` و `labels` مرئياً في السجل، وهو فرقٌ مقصود لا تكرار.

## 2) المواضع هي الحقيقة، و `text` نسخة للراحة

`source.start_char` و `source.end_char` هما الحقيقة: بداية شاملة ونهاية حاصرة، أي الفاصل النصف المفتوح `[start, end)` على **النص المصدري مفكوك الترميز UTF-8، حرفاً بحرف**. و `text` نسخة مطابقة للتسهيل فقط، ويعيد أي قارئ التحقق منها بسطر واحد.

بايثون:

```python
src = open("data/raw/tafsircenter/2_255.txt", "rb").read().decode("utf-8")
assert src[rec["source"]["start_char"]:rec["source"]["end_char"]] == rec["text"]
```

جافاسكربت (Node):

```js
const src = require("fs").readFileSync("data/raw/tafsircenter/2_255.txt", "utf8");
console.assert(src.slice(rec.source.start_char, rec.source.end_char) === rec.text);
```

وتنبيهان مهمّان عند القص:

1. **اقرأ الملف بايتات ثم فكّ الترميز UTF-8** (في بايثون: الوضع الثنائي `"rb"`، أو `open(path, encoding="utf-8", newline="")`). القراءة النصية العادية تحوّل `\r\n` إلى `\n`، فينقص عدد الحروف بمقدار عدد الأسطر وتنزاح كل المواضع. المصدر في هذا المستودع بأسطر CRLF، و `.gitattributes` يمنع جِت من تحويلها.
2. **لا تقصّ على البايتات**: الأرقام تُعدّ حروف يونيكود لا بايتات. في بايثون `str` = حروف يونيكود، وفي جافاسكربت `String.slice` = وحدات UTF-16؛ وهما متطابقان هنا لأن مصادرنا لا تحتوي حرفاً خارج المستوى الأساسي (للتأكد: `[...src].length === src.length`).

إذا اختلف `text` عن الشريحة فالسجل مشبوه: المصدر والأرقام يُرجَّحان، ويُسجَّل الاختلاف في `verification` (`strict_match: false`)، ولا يُنشر السجل حتى يُصحّح.

قيم `verification.text_fidelity` أربع: `exact` مطابق حرفياً · `partial` النص داخل الشريحة لكن الحدود تحتاج مراجعة · `modified` النص مخالف للشريحة (تعديل تحريري) · `not_found` تعذّر الوصول إلى المصدر أو الشريحة. و `normalized_match` قد يكون `true` مع `strict_match: false` (تطابق بعد حذف التشكيل وطيّ المسافات) — وهذا **تنبيه لا نجاح**.

> ملاحظة للتصدير: أي حالة فشل أخرى تُطوى على إحدى هذه القيم الأربع (فشل التحقق ⇒ `not_found` أو `partial`)، لأن المخطط لا يقبل قيماً خارجها.

## 3) لا يُنشر إلا `approved`

| `review.status` | المعنى | ما يجوز فعله |
|---|---|---|
| `ai_proposed` | مقترح آلي خام | عرض داخلي وتدقيق إحصائي فقط. **ليس محتوى** |
| `under_review` | بدأ المختص التعديل | عرض داخلي فقط |
| `approved` | اعتمده مختص | النشر والاستهلاك |
| `rejected` | رفضه مختص | يبقى للسجل والتحليل، لا يُنشر |

عملياً: أي واجهة تعرض «تفسيراً» للناس تقرأ **فقط** السجلات ذات `status == "approved"`، وتستخدم `labels` و `text`، ولا تعرض `ai_proposal` أبداً.

و `review.changes` سجل التدقيق: `at` وقت التغيير (RFC 3339)، و `action` نوعه (مثل `status_approve` أو `resize` أو `label_add`)، و `before` / `after` (أو `from` / `to`) الحالة قبله وبعده، ومعها سياق اختياري: `window` و `highlight_id` و `origin` و `note`. الحقلان `at` و `action` إلزاميان، وأي حقل غير هذه يُرفض. وهذا هو ما تصدّره واجهة المراجعة كما هو دون تحويل.

## 4) كيف تضيف تفسيراً آخر (الطبري، البغوي، ابن عاشور)

الصيغة نفسها تعمل بلا أي تعديل. الخطوات:

1. **ثبّت النص:** ملف نصي عادي لكل آية، واحفظ بصمة `sha256` لملف المصدر (بايتاته كما نزلت، بلا تحويل أسطر).
2. **اختر معرّفاً مستقراً** `tafsir.id`: حروف صغيرة، وشرطة سفلية أو عادية — `al_tabari`, `al_baghawi`, `ibn_ashur`.
3. **سمِّ المصدر** في `source.source_id` بالعُرف نفسه: `<tafsir.id>_<surah>_<ayah>`.
4. **قطّع النص إلى وحدات ثم وسمها:** يقترح المصنّف (`ai_proposal`) ويراجع المختص (`labels`). لا تتغير الصيغة، ولا يُضاف حقل جديد.
5. **`annotation_id`** يبدأ بمعرّف التفسير: `<tafsir.id>-<window key>-<move id>`.

| التفسير | `tafsir.id` | `source_id` مثال | `annotation_id` مثال |
|---|---|---|---|
| ابن كثير | `ibn_kathir` | `ibn_kathir_2_255` | `ibn_kathir-2_255_tafsir-m20` |
| الطبري | `al_tabari` | `al_tabari_2_255` | `al_tabari-2_255_tafsir-m07` |
| البغوي | `al_baghawi` | `al_baghawi_2_255` | `al_baghawi-2_255_tafsir-m03` |
| ابن عاشور | `ibn_ashur` | `ibn_ashur_2_255` | `ibn_ashur-2_255_tafsir-m11` |

ملاحظتان:

- **اختبار الاستقلال عن ابن كثير:** ابحث في `schema/annotation.schema.json` عن `ibn` فلن تجد شيئاً؛ لا اسمَ تفسيرٍ في المخطط ولا في قواعد التحقق. إن ظهر اسم تفسير داخل كود المتحقّق فالتصميم خاطئ.
- **كل تفسير له تثبيته المستقل:** بصمة مستقلة، ونص مستقل، وحواشي محققه مستقلة (كلام المحقق ليس كلام المؤلف). لا تخلط نصّي تفسيرين في ملف مصدر واحد؛ عند الخلط تفسد المواضع ولا يمكن التحقق.

## 5) جدول الوسوم (الرمز ← الاسم)

**طبقة المنهج `source_method`** — بماذا استدلّ المؤلف؟ (تعدد الوسوم مسموح، وقد تكون فارغة إذا كان المقطع تخريجاً أو محتوىً محضاً)

| الرمز | الاسم | التعريف المختصر |
|---|---|---|
| `M_QURAN` | قرآن بالقرآن | آية تُستشهد لبيان معنى الآية (لا اقتباس آية داخل حديث) |
| `M_SUNNAH` | سنة | قول أو فعل أو تقرير نبوي يفسّر الآية أو يبيّن فضلها |
| `M_SAHABA` | صحابة | قول صحابي نفسه مادةً تفسيرية (لا مجرد اسمه في السند) |
| `M_TABIIN` | تابعون | قول تابعي نفسه مادةً تفسيرية (لا مجرد راوٍ) |
| `M_LUGHA` | لغة وغريب | شرح لفظ أو استعمال عربي أو شاهد شعري للمعنى |
| `M_QIRAAT` | قراءات | اختلاف قراءة يبيّن اللفظ أو المعنى |
| `M_NUZUL` | أسباب نزول | خبر يربط حدثاً أو سؤالاً بنزول الآية |
| `M_SIRA` | مغازي وسير | واقعة من السيرة تُستخدم لشرح خطاب الآية |
| `M_ISRAILIYYAT` | إسرائيليات | مادة يعزوها النص لأهل الكتاب أو يصنّفها المؤلف كذلك |
| `M_RAY` | رأي واجتهاد | استنتاج المؤلف أو ترجيحه التفسيري |

**طبقة المحتوى `content_type`** — ماذا يحتوي المقطع؟

| الرمز | الاسم | التعريف المختصر |
|---|---|---|
| `C_FIQH` | فقه وأحكام | استنباط أو بيان حكم شرعي مرتبط بالآية |
| `C_BALAGHA` | بلاغة | تحليل أسلوب أو ظاهرة بلاغية في الآية |
| `C_SHIR` | شعر | بيت أو شاهد شعري للاستدلال اللغوي أو البلاغي |
| `C_FADAIL` | فضائل | فضل سورة أو آية أو أثر قراءتها |
| `C_TAKHRIJ` | تخريج وحكم حديثي | عزو الحديث أو المقارنة بين طرقه أو الحكم على إسناده |
| `C_NUZUL` | أسباب نزول | رواية سبب النزول (محتوىً) |
| `C_ISRAILIYYAT` | إسرائيليات | مضمون المادة الإسرائيلية (محتوىً) |
| `C_TAFSIR` | بيان معنى | شرح مباشر لمعنى لفظ أو جملة من الآية |

الطبقتان مستقلّتان: قد يكون المقطع `M_SUNNAH` و `C_FADAIL` معاً، وقد يكون `M_ISRAILIYYAT` و `C_ISRAILIYYAT` معاً. لا تفترض وسماً واحداً، ولا تُجبر مقطع تخريج محض على منهج.

الشرط الوحيد: **ألا تكون القائمتان فارغتين معاً** في السجل المعتمد، ويعبّر عنه المخطط بـ `anyOf`. أما في `ai_proposal` فالتخلّي مسموح: قد يمتنع المصنّف فيكون `certainty: insufficient` والقائمتان فارغتين، ويُحفظ ذلك كما هو لأن المقترح شهادة على ما حدث لا محتوىً منشوراً.

## 6) الترخيص والإسناد

- نص تفسير ابن كثير هنا من **بيانات مركز تفسير للدراسات القرآنية** المفتوحة (`tafsircenter/tafsir-mcp-data`)، بترخيص **CC BY 4.0**.
- **الإسناد مطلوب** عند النشر: «Tafsir Center for Quranic Studies (https://tafsir.net)» — وتفاصيل المصادر والخطوط في `ATTRIBUTION.md`.
- ما أضفناه (التقطيع، والوسوم، ونتائج التحقق) بيانات مشتقة، بالترخيص نفسه CC BY 4.0. **لم نغيّر حرفاً من النص.**
- كل تفسير جديد يُضاف يُراجع ترخيصه بنفسه؛ لا يُورَّث ترخيص ابن كثير تلقائياً.
- الكود في هذا المستودع بترخيص MIT (`LICENSE`) — وهو ترخيص منفصل عن النصوص والبيانات.

## 7) كيف تتحقق أنت؟

```bash
python -m pip install jsonschema
python -c "import json,jsonschema;S=json.load(open('schema/annotation.schema.json',encoding='utf-8'));R=json.load(open('schema/example_approved.json',encoding='utf-8'));jsonschema.Draft202012Validator(S).validate(R);print('valid')"
```

وللتحقق من النص نفسه (المصدر مقابل `text`) استعمل سطري بايثون في القسم 2. والمثال المرفق `schema/example_approved.json` من تفسير ابن كثير ٢:٢٥٥، المقطع `m20`، وقد حُقّق:

| الفحص | النتيجة |
|---|---|
| `schema/annotation.schema.json` صالح كمخطط (meta-schema) والسجل صالح عليه | ✅ |
| `text` == `2_255.txt[23720:23786]` حرفاً بحرف | ✅ |
| بصمة ملف المصدر == `source.sha256` | ✅ |
| حالة المراجعة `approved` | ✅ (اعتمادٌ في المثال فقط؛ لم يعتمد متخصص الوحدات التجريبية بعد) |

**حدود معروفة للمخطط:** JSON Schema draft 2020-12 لا يعبّر عن علاقات حسابية بين الحقول، لذلك ثلاثة شروط تُفحص في الكود لا في المخطط، وهي موثّقة في `$comment` داخله: `end_char > start_char`، و `ayah_end >= ayah`، وتطابق `text` مع شريحة المصدر. والأمثلة الثلاثة نفسها محقّقة في مثالنا.

---

## English — quick reference

- **What it is.** A tafsir-independent, UI-independent JSON format for one verified annotation unit: a pinned source text (`source.source_id` + `source.sha256`), the machine's proposal (`ai_proposal`), and the human-approved labels (`labels`, `review.status`). Any Quran app, database, REST API, research dataset or MCP server can consume it with no AI and no UI.
- **Three layers, never mixed.** The source text is never re-typed: both the proposal and the approved record carry offsets (`start_char`, `end_char`, Python slice semantics, Unicode code points) into the pinned file. `text` is only a convenience copy and must equal `source[start_char:end_char]`.
- **Offsets are the truth.** Python: `open(p, "rb").read().decode("utf-8")[s:e] == rec["text"]`. JavaScript: `fs.readFileSync(p, "utf8").slice(s, e) === rec.text`. Read bytes then decode UTF-8 — never let a reader translate CRLF to LF, because each removed `\r` shifts every later offset by one. Slice characters, not bytes.
- **Only `approved` is publishable.** `ai_proposed` and `under_review` are working states, `rejected` is kept for audit; none of them is content.
- **Adding a tafsir** (al-Tabari, al-Baghawi, Ibn Ashur) needs no schema change: a new `tafsir.id`, a new `source_id` (`<tafsir_id>_<surah>_<ayah>`), a new `sha256` pin, same record shape. Search the schema for `ibn` — you will not find it.
- **Labels.** `M_*` = the evidence the author used (Quran by Quran, Sunna, Companions, Successors, language and rare words, variant readings, occasions of revelation, sira, Israiliyyat, opinion); `C_*` = what the passage contains (fiqh, rhetoric, poetry, virtues, hadith verification, occasions of revelation, Israiliyyat, meaning). Several labels per set are normal; an approved record must carry at least one label across the two sets, while the AI proposal may carry none because the classifier is allowed to abstain.
- **Schema limits.** Draft 2020-12 cannot express arithmetic between fields, so `end_char > start_char`, `ayah_end >= ayah` and the `text` == slice equality are code-level checks — documented in the schema's `$comment` and enforced by any conforming exporter.
- **License.** Ibn Kathir text: Tafsir Center for Quranic Studies open data, CC BY 4.0 — attribution required. Derived annotations: CC BY 4.0. Code: MIT. See `ATTRIBUTION.md`.
- **Files.** `schema/annotation.schema.json` (draft 2020-12, `additionalProperties: false` at every object level), `schema/example_approved.json` (one real approved record, from 2:255 / `m20`), `docs/DATA_FORMAT.md` (this document).

---

## أداة التصدير

```bash
python src/export_approved.py ui_export.json --out approved.json [--include-rejected]
```

المدخل المقبول (أيّ شكل واحد):
1. مصفوفة سجلات JSON
2. كائن الواجهة الكلاسيكية: `{ "data_version": "<12 hex>", "records": [ ... ] }` من زر «تصدير كل المعتمد»
3. كائن فيه `"annotations": [ ... ]` (وقد يحمل `data_version` أيضاً)
4. سجل واحد (كائن فيه `annotation_id`)

إن وُجد `data_version` في المغلف، يُقارَن بـ `data_version` المضمَّن في `web/fahras.html` (بناء `build_fahras`). عند الاختلاف: **لا يُكتب شيء**، ورسالة عربية ثابتة `نسخة البيانات مختلفة — أعد التحقق من القرارات`، ورمز الخروج **2**. التجاوز الاختياري غير الافتراضي: `--allow-version-mismatch`.

لا يُكتب إلا سجل `approved` اجتاز المخطط، ثم أُعيد التحقق من بصمة ملف المصدر ومن `text == source[start_char:end_char]` ومن `end_char > start_char`؛ وما سِواه يُطبع في التقرير بسببه. ومع `--include-rejected` يُضاف `rejected` فقط، ولا يُصدَّر `ai_proposed` ولا `under_review` أبداً.
المخرج مصفوفة مرتّبة بـ (سورة، آية، `start_char`)، وعند تكرار `annotation_id` يُحفظ الأحدث `review.reviewed_at`. مجموعة معتمدة فارغة (لا سجلات مختارة/صالحة، بما فيها `records: []`) تكتب حرفياً `[]` وتخرج برمز **0**. رموز الخروج: **0** إذا لم يُسقَط سجل، و**1** إذا أُسقط سجل بعد الفحص، و**2** لخطأ المدخل أو اختلاف النسخة. والفحص: `python -m unittest discover -s tests -p "test_export_approved.py"`.



