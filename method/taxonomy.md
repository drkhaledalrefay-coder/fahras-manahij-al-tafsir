# Tafsir Annotation Taxonomy (v0.1, from pilot sheet)

A unit gets tags from BOTH layers. Multiple tags per layer are allowed.

## Layer 1 — Source / Method (مصدر التفسير)

| id | الوسم | التعريف التشغيلي |
|---|---|---|
| S_QURAN | تفسير القرآن بالقرآن | استخدام آية/آيات لتفسير معنى الآية محل التفسير، لا مجرد ورود اقتباس قرآني. |
| S_SUNNAH | تفسير القرآن بالسنة | استدلال بقول/فعل/تقرير منسوب للنبي ﷺ في تفسير الآية أو بيان فضلها/حكمها المرتبط بها. |
| S_SAHABA | أقوال الصحابة | قول صحابي مستخدم كمادة تفسيرية/بيانية، لا مجرد اسم صحابي في الإسناد. |
| S_TABIIN | أقوال التابعين | قول تابعي مستخدم كمادة تفسيرية/بيانية، لا مجرد راوٍ في سلسلة الإسناد. |
| S_LUGHA | اللغة | تحليل لغوي/معجمي/اشتقاقي يخدم فهم الآية. |
| S_RAY | الاجتهاد والرأي | تحليل أو ترجيح تفسيري للمفسر لا يندرج تحت مصدر نقلي محدد. |
| S_IRAB | الإعراب | تحليل نحوي/إعرابي مباشر لألفاظ الآية. |

## Layer 2 — Content Type (نوع المحتوى)

| id | الوسم | التعريف التشغيلي |
|---|---|---|
| C_NUZUL | أسباب النزول | رواية أو بيان يتعلق بسبب نزول الآية أو سياق نزولها. |
| C_FIQH | فقه وأحكام | استنباط أو بيان حكم شرعي مرتبط بالآية. |
| C_BALAGHA | بلاغة | تحليل لأسلوب أو ظاهرة بلاغية في الآية. |
| C_SHIR | شعر | بيت/شاهد شعري أو إحالة إلى الشعر للاستدلال اللغوي/البلاغي. |
| C_ISRAILIYYAT | إسرائيليات | مادة مصنفة علميًا ضمن الإسرائيليات وفق معيار يقره المختص. |
| C_FADAIL | فضائل القرآن/الآية | رواية أو تقرير في فضل سورة أو آية أو أثر قراءتها. |
| C_TAKHRIJ | تخريج/حكم حديثي | إحالة لمصدر الحديث أو مقارنة طرقه أو حكم على إسناده/روايته. |
| C_TAFSIR | بيان معنى | شرح مباشر لمعنى لفظ أو جملة من الآية لا يندرج تحت ما سبق. |

## Hard-case rules (mandatory)

1. **A verse quoted inside a hadith is NOT S_QURAN.** S_QURAN only when a verse is used to explain the meaning of the verse under commentary.
2. **A Companion's or Successor's name inside an isnad is NOT S_SAHABA / S_TABIIN.** Tag them only when their own statement is used as explanatory material.
3. **Strangeness of a report is NOT enough for C_ISRAILIYYAT.** Tag it only when the text itself attributes the material to Ahl al-Kitab / Bani Isra'il sources, or the mufassir explicitly classifies it so.
4. **Takhrij is its own unit.** Separate "رواه فلان / صحيح الإسناد / في إسناده ضعف" from the hadith text itself and tag C_TAKHRIJ.
5. **Low confidence is a valid answer.** If unsure, say so (confidence < 0.6) and explain — it routes the unit to the specialist first.
