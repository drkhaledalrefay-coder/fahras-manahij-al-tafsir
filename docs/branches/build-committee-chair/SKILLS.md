# المهارات والأدوات المستخدمة — build/committee-chair

يوثق هذا الملف المهارات والأدوات التي استُخدمت في تطوير وتدقيق وتوثيق فرع رئيس اللجنة (`build/committee-chair`).

| المهارة / الأداة | لماذا استُخدمت في هذا الفرع | أين ملفها أو مصدرها |
|---|---|---|
| **vibe-coding-project-auditor** | تدقيق الجاهزية والصلابة الهندسية للفرع، وفحص المتانة ومراجعة الملاحظات وتصنيفها وإغلاق ملاحظات P1 وP2 قبل الدمج. | `docs/team/skills/vibe-coding-project-auditor/SKILL.md` |
| **negative-testing-guard** | تطبيق مبدأ اختبارات الفشل السابقة (fail-before proof)؛ تخصيص اختبار سلبي محدد لكل قاعدة تحكيم حتمية لمنع الانحدار. | `docs/team/SKILLS.md` ومسار `tests/test_committee_chair.py` |
| **diataxis-documentation** | صياغة وثيقة التسليم `HANDOFF.md` كدليل إجرائي عملي ومرجع موجز بلا حشو، والالتزام الصارم بسقف الأسطر (≤ ٨٠ سطراً). | https://diataxis.fr |
| **wcag-accessibility & web-guidelines** | توجيه تصميم الإنفوجرافيك `usage.html` وفق معايير WCAG 2.2 AA (تباين الألوان ≥ 4.5:1، دعم RTL، خط النظام العربي، استيعاب أبعاد 1600×900). | https://www.w3.org/WAI/standards-guidelines/wcag/ و`briefs/web-interface-guidelines.md` |
| **playwright-qa** | التقاط لقطة الإنفوجرافيك `usage.png` بدقة 1600×900 عبر Chromium آلياً، والتحقق البصري من سلامة الحروف والتخطيط بدون قص. | https://playwright.dev |
