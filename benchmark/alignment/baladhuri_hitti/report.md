# PD alignment slice -- al-Baladhuri / Hitti

First vertical slice of **D1e option (d)**: aligned benchmark passages extracted from a public-domain translation pair. ONE work, end to end.

- Arabic: OpenITI `0279Baladhuri.FutuhBuldan`
- English: Philip K. Hitti, The Origins of the Islamic State, vol. 1 (New York: Columbia University Press, 1916); archive.org originsofislamic01albauoft
- Genre (`021.BookSUBJ`, read from the OpenITI header, not inferred): **التاريخ** (*al-tarikh*, history) -- a genre v0.1-draft does not contain at all
- Author death year (`011.AuthorDIED`): **279 AH**
- Rights: `PD_US_PRE_1930_PUBLICATION` -- English: Hitti 1916, Columbia University Press, published pre-1930 -- US public domain by publication date. Arabic: pre-modern text (author d. 279 AH) digitised by OpenITI from Shamela 0012221. Neither claim is cleared legal advice; D6b still gates commercial use.
- Selection seed: `20260814`

## Pipeline yield

| stage | count |
|---|---|
| Arabic `### \|` sections in the OpenITI text | 90 |
| English Part/Chapter units parsed from the scan | 70 |
| section <-> chapter pairs confirmed | 39 |
| khabar-level cuts (matched transmitter names) | 199 |
| passages assembled between cuts | 109 |
| passages selected for the benchmark | 39 |

## Selected passages

| band | count |
|---|---|
| 100-250 | 30 |
| 250-600 | 9 |

| method | count |
|---|---|
| llm_proposed | 18 |
| structural | 21 |

Median confidence: **0.85**.

## What the confidence means

Every passage begins and ends at a *cut*: a point where an English paragraph's abridged isnad matches the head of an Arabic paragraph by transliterated transmitter name. A passage is therefore bracketed at both ends by independent name evidence, which is what makes the classic failure -- a systematic one-report shift that looks plausible row by row -- structurally hard rather than merely unlikely. `confidence` is the weaker of its two brackets, discounted when the English/Arabic word ratio falls outside Hitti's normal 0.85-2.30.

`method=structural` means the brackets alone carried it. `method=llm_proposed` means the structural confidence was below 0.8 and Claude was asked whether the English translates the Arabic; the verdict and the model's own confidence are recorded per item, and the structural confidence is preserved alongside it. No LLM judgement is ever written as if it were an anchor match.

## Known limits

- **Volume 1 only.** Hitti's vol. 1 covers roughly the first 70 of the 90 Arabic sections. Murgotten's vol. 2 is a separate scan and has not been validated here.
- **Chapter coverage is partial by design.** Sections whose chapter could not be confirmed by both title evidence and khabar-level cuts are dropped, never assigned to the nearest chapter.
- **OCR damage persists inside passages.** The 1916 scan mangles proper names ('Busy a' for 'Busra'); footnote and running-head stripping is rule-based and is not perfect. The review page exists to surface what survived.
- **Hitti abridges.** He states in his own footnote that isnads are cut to first and last authority, and he omits the occasional report. Passages where that happens show up as a low word ratio and are flagged, but a short omission inside a long passage will not be.

Unconfirmed Arabic sections: 51 of 90.

## Per-chapter detail

Arabic section titles are deliberately omitted from this table: it is repo-tracked, and the standing rule keeps corpus text out of the repo even when it is only a heading. The English chapter titles below are bibliographic metadata from a 1916 public-domain table of contents.

| Arabic section # | English chapter | Ar paras | En paras | cuts | passages |
|---|---|---|---|---|---|
| 0 | PART I / CHAPTER I -- Al-Madinah | 21 | 57 | 6 | 4 |
| 1 | PART I / CHAPTER II -- The Possessions of the banu-an-Nadir | 14 | 17 | 5 | 3 |
| 2 | PART I / CHAPTER III -- The Possessions of the banu-Kuraizah | 3 | 4 | 1 | 0 |
| 3 | PART I / CHAPTER IV -- Khaibar | 12 | 28 | 7 | 4 |
| 4 | PART I / CHAPTER V -- Fadak | 13 | 23 | 8 | 4 |
| 6 | PART I / CHAPTER VII -- Makkah | 30 | 50 | 16 | 10 |
| 7 | PART I / CHAPTER VIII -- The Wells of Makkah | 30 | 20 | 9 | 4 |
| 8 | PART I / CHAPTER IX -- The Floods in Makkah | 10 | 5 | 2 | 0 |
| 10 | PART I / CHAPTER XI -- Tabalah and Jurash | 1 | 1 | 0 | 0 |
| 11 | PART I / CHAPTER XII -- Tabuk, Ailah, Adhruh, Makna and al-Jarba' | 3 | 5 | 1 | 0 |
| 12 | PART I / CHAPTER XIII -- DUMAT AL-jANDAL | 8 | 6 | 2 | 1 |
| 16 | PART I / CHAPTER XVII -- Al-Bahrain | 29 | 25 | 12 | 7 |
| 19 | PART I / CHAPTER XX -- The Apostasy of the banu-Wali'ah and al-Ash'ath | 15 | 12 | 3 | 2 |
| 22 | PART II / CHAPTER II -- The Advance of Khalid ibn-al-Walid on Syria and iio | 8 | 13 | 3 | 1 |
| 23 | PART II / CHAPTER III -- The Conquest of Busra | 2 | 3 | 1 | 0 |
| 24 | PART II / CHAPTER IV -- The Battle of Ajnadin (or Ajnadain) | 3 | 5 | 0 | 0 |
| 27 | PART II / CHAPTER VII -- The Battle of Marj as-Suffar | 17 | 5 | 3 | 1 |
| 30 | PART II / CHAPTER X -- The Battle of al-Yarmuk | 9 | 10 | 3 | 2 |
| 32 | PART II / CHAPTER XII -- The Province of Kinnasrin and the cities called | 14 | 29 | 9 | 7 |
| 35 | PART II / CHAPTER XV -- Al-Jarajimah | 6 | 12 | 3 | 2 |
| 38 | PART III / CHAPTER II -- The Christians of the banu-Taghlib ibn-Wa'il | 7 | 8 | 4 | 2 |
| 42 | PART IV / CHAPTER I -- The Conquest of Armenia | 32 | 55 | 18 | 9 |
| 45 | PART V / CHAPTER III -- The Conquest of Barkah and Zawilah | 7 | 8 | 5 | 3 |
| 47 | PART V / CHAPTER V -- The Conquest of Ifrikiyah | 12 | 15 | 5 | 4 |
| 49 | PART VI / CHAPTER I -- The Conquest of Andalusia | 6 | 22 | 6 | 4 |
| 54 | PART IX / CHAPTER II -- The Caliphate of 'Umar ibn-al-Khattab | 1 | 3 | 1 | 0 |
| 55 | PART IX / CHAPTER III -- The Battle of Kuss an-Natif, or the Battle of al-Jisr | 5 | 6 | 1 | 0 |
| 56 | PART IX / CHAPTER IV -- The Battle of Mihran or an-Nukhailah | 4 | 8 | 3 | 2 |
| 57 | PART IX / CHAPTER V -- The Battle of al-KadisIyah | 49 | 21 | 7 | 5 |
| 58 | PART IX / CHAPTER VI -- The Conquest of al-Mada'in | 5 | 7 | 3 | 1 |
| 60 | PART IX / CHAPTER VIII -- The Founding of al-Kufah | 37 | 81 | 23 | 15 |
| 62 | PART IX / CHAPTER X -- Al-Bata'ih | 6 | 10 | 2 | 0 |
| 63 | PART IX / CHAPTER XI -- Mad'inat as-Salam | 11 | 28 | 3 | 0 |
| 65 | PART X / CHAPTER I -- HULWAN | 2 | 5 | 1 | 0 |
| 66 | PART X / CHAPTER II -- The Conquest of Nihawand | 14 | 10 | 6 | 3 |
| 67 | PART X / CHAPTER III -- Ad-Dinawar, Masabadhan and Mihrijankadhaf | 5 | 8 | 4 | 2 |
| 68 | PART X / CHAPTER IV -- The Conquest of Hamadhan | 6 | 8 | 5 | 3 |
| 69 | PART X / CHAPTER V -- Kumm, Kashan and Isbahan | 8 | 15 | 6 | 3 |
| 70 | PART X / CHAPTER VI -- The Death of Yazdajird ibn-Shahriyar ibn-Kisra | 4 | 34 | 2 | 1 |

Review page (contains corpus text, lives outside the repo): `~/versed-translator-data/benchmark-alignment/baladhuri_hitti/review.html`. 109 passages are rendered there, including the 70 not selected.
