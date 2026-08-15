# PD alignment slice -- Miskawayh / Margoliouth & Amedroz

Year-anchored proposals from *Tajarib al-Umam* against *The Eclipse of the 'Abbasid Caliphate* (1921). Corpus text lives off-repo.

- Arabic: OpenITI `0421Miskawayh.Tajarib`
- English: The Eclipse of the 'Abbasid Caliphate, ed. and trans. H. F. Amedroz and D. S. Margoliouth, vols IV-V (Oxford: Basil Blackwell, 1921); archive.org eclipseofabbasid04ameduoft, eclipseofabbasid05ameduoft
- Rights: `PD_US_PRE_1930_PUBLICATION` -- English: Margoliouth & Amedroz, Basil Blackwell, Oxford, 1921 -- title page read inside both scans; published pre-1930, so US public domain by publication date. Arabic: pre-modern text (author d. 421 AH) digitised by OpenITI from Shamela 0012396. Neither claim is cleared legal advice; D6b still gates commercial use.
- Selection seed: `20260815`

## Pipeline yield

| stage | count |
|---|---|
| Arabic hijri years parsed | 71 |
| English hijri years parsed | 73 |
| shared year-blocks | 69 |
| years used | 59 |
| years rejected | 10 |
| proposals assembled | 504 |
| selected after aligned verdict | 24 |

## Selected passages

| band | count |
|---|---|
| 100-250 | 15 |
| 250-600 | 9 |

| method | count |
|---|---|
| llm_proposed | 24 |

## Evidence and limits

The hijri year is a real bilateral anchor (Arabic year headings; English `A.H. NNN` running heads). Cuts *inside* a year are name-refined proportional proposals, not structural brackets. Every selected item has an explicit `aligned` content verdict; `reference_fidelity` remains `pending_human_audit`.

A missed year heading on either side is dropped via word-ratio tolerance, not quietly merged. The English running head can lag a page, so within-year offset is expected; that is why adjudication is mandatory and why a proposal is not a passage.

Review pages (corpus text, off-repo): `~/versed-translator-data/benchmark-alignment/miskawayh_eclipse/review.html` (triage, worst first) and `review_shipping.html` (selected only, best first). 504 proposals rendered; 24 selected.

Rejected years: 10 of 69.
