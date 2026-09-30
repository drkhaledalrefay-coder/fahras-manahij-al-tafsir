# Task A — Multi-tafsir sources

Deterministic extract + layer/span/window build for three additional tafsirs. Ibn Kathir pipeline outputs were not regenerated.

DB: `quran.db` sha256 `10e61f615ab5…` (verified against `data/raw/manifest.json`).

## Per tafsir × verse

| tafsir | verse | raw chars | sha256 (12) | layout ranges | apparatus (by subtype) | author spans | window rule | window chars | window spans |
|---|---|---:|---|---:|---|---:|---|---:|---:|
| al_tabari | 2:255 | 25694 | `2562fce7247b` | 135 | editor_bracket=4, footnote=78, unknown_marker=1, verse_ref=2 | 403 | `all_spans_capped_110` | 6346 | 110 |
| al_tabari | 2:102 | 84095 | `abccb5ec7784` | 231 | editor_bracket=52, footnote=341, verse_ref=8 | 1087 | `first_harut_cap_40` | 2709 | 40 |
| al_tabari | 17:105 | 865 | `246341ff0183` | 4 | (none) | 8 | `all_spans` | 857 | 8 |
| al_saadi | 2:255 | 2859 | `cc0941c3aec1` | 0 | footnote=1 | 18 | `all_spans_capped_110` | 2859 | 18 |
| al_saadi | 2:102 | 2935 | `46aaa66d05f6` | 0 | (none) | 23 | `first_harut_cap_40` | 2935 | 23 |
| al_saadi | 17:105 | 402 | `598d65f463e9` | 0 | (none) | 5 | `all_spans` | 402 | 5 |
| al_baghawi | 2:255 | 12667 | `c10659999eee` | 0 | editor_bracket=1, footnote=9 | 57 | `all_spans_capped_110` | 12667 | 57 |
| al_baghawi | 2:102 | 18892 | `3e0e69bb068d` | 0 | editor_bracket=4, footnote=16 | 102 | `first_harut_cap_40` | 9204 | 40 |
| al_baghawi | 17:105 | 173 | `c81bf8c8176a` | 0 | (none) | 1 | `all_spans` | 173 | 1 |

### Notes on window rules

- **2_255:** searched for phrase-by-phrase commentary starting at «لا تأخذه سنة» with the same needles as `select_2_255_tafsir` (start + «وقوله» same/prev, end last «العلي العظيم», cap 110). None of the three tafsirs satisfied the start-anchor pair, so all used `all_spans_capped_110`.
- **2_102:** first AUTHOR span whose normalized text contains «هاروت», then up to 40 spans.
- **17_105:** all AUTHOR spans.

## Markup / bracket pattern survey (all 9 files)

### HTML / layout tags

- `<br>` × 383

### Footnotes `¬…¥`

- closed footnote pairs × **445**

### `[asN]` markers (subtype `unknown_marker` — meaning not guessed)

- `[as2]` × 1

### Verse-ref brackets (subtype `verse_ref`)

- `[غافر: 7]` × 2
- `[الأحزاب: 37]` × 1
- `[البقرة: 279]` × 1
- `[الحشر: 12]` × 1
- `[الزمر: 67]` × 1
- `[الشورى: 5]` × 1
- `[طه: 66]` × 1
- `[طه: 71]` × 1
- `[يونس: 30]` × 1

### Other square brackets (subtype `editor_bracket`)

Total distinct patterns: **59** (each ×1 unless noted). Full list:

- ×1 `[348]`
- ×1 `[أخبرَ عنهم أنهم]`
- ×1 `[أفْرِكى. فأفْرَكَتْ]`
- ×1 `[ألَا تهلِكُهم]`
- ×1 `[أنصباءَ وأنصباءَ]`
- ×1 `[أهلُ التأويلِ]`
- ×1 `[أي: لمَن استحبَّه]`
- ×1 `[أَيْ إِلْهَامًا وَعِلْمًا، فَالْإِنْزَالُ بِمَعْنَى الْإِلْهَامِ وَالتَّعْلِيمِ، وَقِيلَ: وَاتَّبَعُوا مَا أُنْزِلَ عَلَى الْمَلَكَيْنِ]`
- ×1 `[إنى سأُحدِّثُكم عن]`
- ×1 `[الآية ¬ذكره ابن كثير في تفسيره 1/ 195. وهو في سيرة ابن هشام 1/ 544 مختصرًا.¥.<br>وحدَّثني محمدُ بنُ سعدٍ، قال: حدَّثني أبى، قال: حدَّثني عمى، قال: حدَّثني أبى، عن أبيه، عن ابنِ عباسٍ: {وَاتَّبَعُوا مَا تَتْلُو الشَّيَاطِينُ]`
- ×1 `[الحسينُ بنُ عمرِو بنِ محمدٍ العَنْقزىُّ]`
- ×1 `[الحسينُ، قال: حدَّثنى]`
- ×1 `[الحيوانَ والجمادَ]`
- ×1 `[الذي يمشِى يُحَرِّشُ ¬حرش بينهم: أفسد وأغرى بعضهم ببعض. التاج (ح ر ش).¥]`
- ×1 `[الرُّقَادِ وعندَ]`
- ×1 `[الشهَواتِ التي كانت]`
- ×1 `[انظر: لسان العرب مادة: أخذ]`
- ×1 `[بجهلِ ما]`
- ×1 `[تتَّبِعُ وتأتمُّه]`
- ×1 `[ثم قال]`
- ×1 `[جاءت في شأْنِ]`
- ×1 `[جلَّ ثناؤُه بقولِه]`
- ×1 `[دون الخبرِ عنهم أنهم اتَّبَعوا ما تَلَته الشياطينُ من ذلك أيامَ نوحٍ وأيامَ موسى؟<br>قيل: إنما أخبَر اللهُ بذلك، تعالى ذكرُه، عن اتِّباعِهم ما تَلَتْهُ الشياطينُ على عهدِ سليمانَ]`
- ×1 `[ذَهابِهم عن]`
- ×1 `[عذابَ الدنيا من عذابِ]`
- ×1 `[عرَفوا أنه]`
- ×1 `[فأبرَأ اللهُ]`
- ×1 `[فأرْبَبْتُ وأبيتُ]`
- ×1 `[فقال: ألا تعلمُ]`
- ×1 `[فلم يألُوا]`
- ×1 `[فيه، فيتبيَّنُه]`
- ×1 `[فَكُتِبَ ذَلِكَ]`
- ×1 `[قال: قولُه: {فَلَا تَكْفُرْ}]`
- ×1 `[قلتُ: لا]`
- ×1 `[لقولِ جميعِ]`
- ×1 `[ملَكين ليهبِطَا]`
- ×1 `[من السحرةِ لم تَزَلْ]`
- ×1 `[من كذا، كذا وكذا]`
- ×1 `[موسى صلواتُ اللهِ عليه]`
- ×1 `[نحوِ ما ذكرْنا]`
- ×1 `[وأراده]`
- ×1 `[وأمرِهما]`
- ×1 `[والأغلالُ]`
- ×1 `[والكفرَ]`
- ×1 `[واللهِ]`
- ×1 `[وعملِهم]`
- ×1 `[وقال قائلو هذه المقالةِ: إن اللهَ أنزَل السحرَ على هاروتَ وماروتَ ببابلَ]`
- ×1 `[وقالوا: كفَر سليمانُ]`
- ×1 `[وقد فُتن]`
- ×1 `[وقولُه الآخرُ]`
- ×1 `[وما كفَر سليمانُ]`
- ×1 `[ومن لم يكنْ له خَلاقٌ]`
- ×1 `[وهو عمرانُ]`
- ×1 `[ويذهَبُ]`
- ×1 `[وينعُسُ وينْتبِهُ]`
- ×1 `[وَالْمُتَعَلِّمِ]`
- ×1 `[وَمَا أُنْزِلَ عَلَى الْمَلَكَيْنِ]`
- ×1 `[وَمَلَكٌ عَلَى صُورَةِ سَيِّدِ الطَّيْرِ وَهُوَ النَّسْرُ يَسْأَلُ الرِّزْقَ لِلطَّيْرِ مِنَ السَّنَةِ إِلَى السَّنَةِ]`
- ×1 `[وَيَأْخُذُهُ عَنْهُمَا وَيَعْمَلُ بِهِ]`

Per-file survey detail is also stored under each `data/multi/<tafsir_id>/layers/<s>_<a>.json` → `survey`.

## License coverage

Does `data/raw/tafsircenter/README.md` CC BY 4.0 cover all tables?

**Yes.** The dataset card licenses the whole SQLite database (all classical tafsirs listed, including Tabari, Baghawi, and Saadi). Quoted:

> ## 📜 License — CC BY 4.0
>
> - ✅ Share, adapt, use commercially
> - 📌 Attribution required: "Tafsir Center for Quranic Studies (https://tafsir.net)"

Front-matter also states `license: cc-by-4.0`. The Content table lists Jami' al-Bayan (الطبري), Ma'alim al-Tanzil (البغوي), and Taysir al-Karim al-Rahman (السعدي) among the classical tafsirs included.

## Scripts / outputs

| step | script | outputs |
|---|---|---|
| 1 | `src/multi_fetch.py` | `data/raw/tafsircenter/{al_tabari,al_saadi,al_baghawi}/*.txt` + manifest append |
| 2 | `src/multi_layers.py` | `data/multi/<id>/layers/*.json` |
| 3 | `src/multi_spans.py` | `data/multi/<id>/spans/*.json` |
| 4 | `src/multi_windows.py` | `data/multi/<id>/windows/*.json` |

