# المساهمة

هذه قواعد العمل داخل المستودع. التفاصيل التنفيذية في [`docs/RUN.md`](docs/RUN.md). تشغيل التصنيف: [`docs/AI_RUN.md`](docs/AI_RUN.md).

## التشغيل محلياً

من جذر المستودع:

```bash
pip install -r requirements.txt
python src/build_fahras.py
python -m http.server 8791 --directory web
```

ثم افتح http://127.0.0.1:8791/fahras.html — الصفحة الرئيسية هي `web/fahras.html`.

## بوابات الجودة

شغّل الخادم على المنفذ 8791 كما فوق، ثم:

```bash
python src/v2_selftest.py
python -m unittest tests.test_export_approved -v
python -m unittest tests.test_classify_api
python -m playwright install chromium
python deck/qa/qa_runner.py
```

`qa_runner.py` وبقية سكربتات `deck/qa/` تتصل بـ http://localhost:8791/fahras.html. اختبار التصدير يتوقع ٢٢ نجاحاً.

## إضافة آيات

لا تُضاف آية بتعديل `web/` يدوياً. اتبع الترتيب في [`docs/RUN.md`](docs/RUN.md): تثبيت النص من `quran.db` عبر `--db`، ثم الطبقات والأجزاء والنوافذ، ثم العلامات والحزم، ثم التصنيف (معرّفات أجزاء فقط؛ انظر [`docs/AI_RUN.md`](docs/AI_RUN.md))، ثم الفاحص الحتمي، ثم `python src/build_fahras.py`.

## قواعد

- لا نص تفسير مولَّد. النموذج لا يكتب حرفاً من المتن ولا يعيد صياغته.
- كل اقتراح من نموذج يُوسم **«مقترح آلي»**. ليس اعتماداً.
- لا يُنشر إلا ما حالته **«معتمد»** بعد مراجعة بشرية. سجلات `approved` التوضيحية ليست اعتماداً.
- **لا مفاتيح API ولا أسرار في أي مكان بالمستودع** (وليس فقط داخل `web/`). المفتاح في متغيّر جلسة الطرفية فقط — انظر [`docs/AI_RUN.md`](docs/AI_RUN.md).
- **لا تُودع `quran.db`**؛ الملف متجاهَل ويُنزَّل محلياً فقط.
- **`web/fahras.html` ملف مولَّد** — للجميع تشغيل `python src/build_fahras.py` محلياً؛ إيداع `web/fahras.html` مقصور على شخص واحد معيَّن. لا تعدّلوه يدوياً.
- كل نموذج يكتب فقط تحت `<base>/moves/<annotator>/`.
- فرع واحد لكل شخص؛ راجع `git diff` قبل كل إيداع.
- أودع (commit) مساراتك أنت فقط. لا `git add` لملفات جلسة أخرى، ولا لملفات الخدش أو الملاحظات الشخصية.

## English

From the repo root: `pip install -r requirements.txt`, then `python src/build_fahras.py`, then `python -m http.server 8791 --directory web`, and open http://127.0.0.1:8791/fahras.html. QA: `python src/v2_selftest.py`, `python -m unittest tests.test_export_approved -v` (22 tests), `python -m unittest tests.test_classify_api`, `python -m playwright install chromium` (once, for QA only), and `python deck/qa/qa_runner.py` against that server. AI classify: [`docs/AI_RUN.md`](docs/AI_RUN.md). To add verses, follow [`docs/RUN.md`](docs/RUN.md) — do not hand-edit `web/`. No generated tafsir text. AI proposals stay labeled «مقترح آلي»; only «معتمد» is publishable. No API keys anywhere in the repo. Never commit `quran.db`. Everyone may run `python src/build_fahras.py` locally; only committing `web/fahras.html` is limited to one designated person. Each model writes only under `<base>/moves/<annotator>/`. One branch per person; `git diff` before every commit.
