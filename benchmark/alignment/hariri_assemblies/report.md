# PD alignment slice -- al-Hariri / Chenery and Steingass

Maqama-anchored proposals from the *Maqamat* against *The Assemblies of Al Hariri* (1867/1898). Corpus text lives off-repo.

- Arabic: OpenITI `0516IbnCaliHariri.Maqamat`
- English: The Assemblies of Al Hariri, trans. Thomas Chenery (vols. I, 1867) and F. Steingass (vol. II, 1898); archive.org the-assembly-of-al-hariri-all-50, notes-free all-50 scan
- Rights: `PD_US_PRE_1930_PUBLICATION` -- English: Chenery 1867 (Williams and Norgate) and Steingass 1898 (Oriental Translation Fund); title page read inside the all-50 scan; both published pre-1930, so US public domain by publication date. Arabic: pre-modern text (author d. 516 AH) OpenITI PRIMARY_VERSION JK009202, cleaned of paratext. Neither claim is cleared legal advice; D6b still gates commercial use.
- Selection seed: `20260815`

## Pipeline yield

| stage | count |
|---|---|
| Arabic maqamat parsed | 50 |
| English assemblies parsed | 50 |
| paired by sequence | 50 |
| maqamat used | 47 |
| maqamat rejected | 3 |
| proposals assembled | 132 |
| selected after aligned verdict | 37 |

## Selected passages

| band | count |
|---|---|
| 100-250 | 17 |
| 250-600 | 20 |

| method | count |
|---|---|
| llm_proposed | 37 |

## Evidence and limits

The maqama is a real bilateral anchor (Arabic maqama headings; English THE NTH ASSEMBLY headings). Printed Arabic numerals in this witness are dirty, so pairing is by document order, not by those labels. Cuts *inside* a maqama are name-refined proportional proposals. Every selected item has an explicit `aligned` content verdict; `reference_fidelity` remains `pending_human_audit`.

Review pages (corpus text, off-repo): `~/versed-translator-data/benchmark-alignment/hariri_assemblies/review.html` (triage, worst first) and `review_shipping.html` (selected only, best first). 132 proposals rendered; 37 selected.

Rejected maqamat: 3 of 50.
