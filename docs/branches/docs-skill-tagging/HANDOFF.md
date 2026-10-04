# تسليم فرع: docs/skill-tagging — مهارة وسم مناهج التفسير

## ١) ماذا تغيّر ولماذا
إضافة مهارة وكيل متخصصة (`tafsir-methods-tagging`) لتعليم مشغّل الذكاء (Ollama) خطوات وسم مناهج التفسير لسورة النور.
تهدف المهارة لضبط التشغيل بالعيّنة (24:35) أولاً ثم التوقف للمراجعة قبل الوسم الجماعي، ومنع أي تعديل يدوي على النصوص.

## ٢) الملفات المتغيرة
- `docs/team/SKILLS.md`: فهرسة المهارة الجديدة وتحديد نطاق استخدامها.
- `docs/team/skills/tafsir-methods-tagging/SKILL.md`: بطاقة المهارة والتعليمات والقواعد الصلبة.
- `docs/team/skills/tafsir-methods-tagging/references/methods.md`: جدول رموز المناهج العشرة ومستويات اليقين.
- `docs/team/skills/tafsir-methods-tagging/references/reason-codes.md`: جدول رموز الامتناع الستة عشر المغلقة.
- `docs/team/skills/tafsir-methods-tagging/references/runbook.md`: دفتر التشغيل وأعلام الأوامر الحقيقية.
- `docs/branches/docs-skill-tagging/`: حزمة الفرع (`HANDOFF.md`, `SKILLS.md`, `usage.html`, `usage.png`).

## ٣) طريقة الاستخدام خطوة بخطوة
١. **تحميل المهارة في الوكيل (Claude Code أو Codex):**
انسخ مجلد `docs/team/skills/tafsir-methods-tagging` إلى دليل مهارات الوكيل (مثل `.claude/skills/` أو مجلد مهارات الوكيل)، أو وجّه الوكيل مباشرة لقراءة ملف `SKILL.md`.
٢. **ضبط بيئة الطرفية للجلسة وسحب النماذج (PowerShell):**
```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:LLM_API_KEY = "ollama"
$env:LLM_BASE_URL = "http://localhost:11434/v1"
ollama pull qwen2.5:32b
ollama pull gemma3:27b
ollama list
```
٣. **الفحص الجاف ثم عيّنة الآية 24:35 على التفاسير الأربعة:**
```powershell
python src/run_window.py --tafsir al_tabari --window 24_35_p01 --base data/nur/al_tabari --dry-run
python src/run_window.py --tafsir al_tabari --window 24_35_p01 --base data/nur/al_tabari --api --model qwen2.5:32b
```
كرر لنوافذ العيّنة (ابن كثير، البغوي، السعدي) ثم **توقّف للمراجعة**.
٤. **الوسم الجماعي والفحص الحتمي (بعد قبول العيّنة):**
```powershell
python src/run_surah.py --db "quran.db" --tafsir al_tabari --surah 24 --base data/nur/al_tabari --classify --time-cap 300
python src/v2_verify.py --base data/nur/al_tabari
```
٥. **الحفظ والتوثيق:** commit واحد لكل تفسير يذكر وسم النموذج الفعلي وتاريخ التشغيل، دون رفع إلى `main`.
قواعد المنهج: لم ندرّب نماذج خاصة؛ يعمل وكيلان من عائلتين مختلفتين، والأرقام أعداد توجيه وليست دقة.

## ٤) كيف تتحقق بنفسك
- تشغيل الفحص الذاتي للتأكد من سلامة منطق المطابقة وعقد الإسناد:
  `python src/v2_selftest.py` ← النتيجة المتوقعة: `SELFTEST PASS`
- التحقق من عدم المساس بأي نص مصدري:
  `git status --porcelain data/` ← النتيجة المتوقعة: مخرجات فارغة تماماً.
- مطابقة الأعلام المستعملة مع مخرجات المساعدة:
  `python src/run_window.py --help` و `python src/run_surah.py --help` و `python src/v2_verify.py --help`

## ٥) ما لم يُنجز / مخاطر
- لم يُشغَّل الوسم الفعلي لسورة النور بعد؛ المهارة توفر تعليمات التشغيل للمشغّل البشري على خادم GPU.
- عتبة الترشيح: الكود يعتمد 75 في `v2_verify.py` بينما الوثيقة تذكر 85؛ يُلتزم بسلوك الكود وتوثيق العتبتين.
- خطر تشغيل عينات دون توقف للمراجعة، أو استخدام نماذج لم تُوثّق وسومها الدقيقة في `committee.json`.

## ٦) التنفيذ والمراجعة
skill written by Cline (cline-free/muse-spark-1.3-contributor), checked by Claude (codes, reason codes, CLI flags all matched to source); package by Antigravity (gemini-3.8-flash-high).
