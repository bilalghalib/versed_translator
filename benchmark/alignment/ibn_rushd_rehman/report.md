# PD alignment slice -- Ibn Rushd / Jamil-ur-Rehman

Treatise-anchored proposals from *Fasl al-Maqal* and the *Damima* against *The Philosophy and Theology of Averroes* (1921). Corpus text lives off-repo.

- Arabic: OpenITI `0595IbnRushdHafid.FaslMaqal` (PRIMARY_VERSION JK010686)
- English: The Philosophy and Theology of Averroes, trans. Mohammad Jamil-ur-Rehman (Baroda: Gaekwad Studies in Religion and Philosophy XI, 1 January 1921); Project Gutenberg ebook 65708
- Rights: `PD_US_PRE_1930_PUBLICATION` -- English: Gutenberg #65708 title page reads Printed by Manibhai Mathurbhai Gupta at the Arya Sudharak Printing Press, Raopura, Baroda, and Published by A. G. Widgery, the College, Baroda, 1-1-1921; translator Mohammad Jamil-ur-Rehman. Published 1921, so US public domain by publication date. Arabic: pre-modern text (author d. 595 AH) OpenITI PRIMARY_VERSION JK010686, cleaned of paratext. Neither claim is cleared legal advice; D6b still gates commercial use.
- Selection seed: `20260815`

## Pipeline yield

| stage | count |
|---|---|
| Arabic treatises parsed | 2 |
| English treatises parsed | 3 |
| paired by treatise | 2 |
| treatises used | 2 |
| treatises rejected | 0 |
| unpaired English treatises | kashf |
| proposals assembled | 25 |
| selected after aligned verdict | 2 |

## Selected passages

| band | count |
|---|---|
| 100-250 | 1 |
| 250-600 | 1 |

| method | count |
|---|---|
| llm_proposed | 2 |

## Evidence and limits

The treatise is a real bilateral anchor (Arabic Damima salutation; English APPENDIX / May God perpetuate). OpenITI FaslMaqal is Fasl plus Damima only. English Gutenberg 65708 also prints Kashf (An Exposition of the Methods of Argument); that treatise is unpaired and was not cut. Cuts *inside* a treatise are name-refined proportional proposals. Every selected item has an explicit `aligned` content verdict; `reference_fidelity` remains `pending_human_audit`.

Review pages (corpus text, off-repo): `~/versed-translator-data/benchmark-alignment/ibn_rushd_rehman/review.html` (triage, worst first) and `review_shipping.html` (selected only, best first). 25 proposals rendered; 2 selected.

Rejected treatises: 0 of 2.
