# Fluency is not fidelity

**Toward failure-aware, cost-aware translation of Classical Arabic**

Versed Research Report **v0.1** · 17 August 2026 · Bilal Ghalib

**What this is.** A shareable account of what we measured. It is written for collaborators, a paper draft, a dataset card, or a model card. It is not a grant proposal and not the operational roadmap.

**How to read claims.** Every number is **measured** unless marked **inferred**, **human judgment**, or **hypothesis**. The laboratory ledger is `TRANSLATION_EXPERIMENTS.md`. Human scores on the 14-passage diagnostic are **judgment**, not a validated metric. Round-1 Fable flags are **silver** (single-model rater), not human gold, and are `train_eligible=false`.

**Phase.** Comparative evaluation and failure discovery is **complete**. Failure-aware translation has **not** begun. No further Fable sittings, glossary runs, Blind-50, or book translation until the questions in §8 decide what evidence we still need.

---

## 1. The problem

Classical Arabic machine translation can produce fluent, complete-looking English that is semantically wrong. A model can finish every block, leave no leftover Arabic, and still invent people, dissolve names into common nouns, invert who did what, or reverse a moral climax.

That is not a fluency problem. It is a **publication-blocking** problem. At corpus scale, even a small rate of those errors is millions of untrustworthy words.

Two questions that people keep collapsing, and that we keep apart:

1. **What is the cheapest way to produce a first large corpus at a quality bar we will defend?**
2. **What open model do we fine-tune and eventually publish?**

They have different answers. Question 2 is constrained: the model we own must be open (TranslateGemma, not a closed API). Question 1 is empirical. This report is about what the first evaluation campaign actually showed — and what it did not.

---

## 2. What we measured (compact)

| Asset | Size | Role |
| --- | --- | --- |
| PD-aligned eval passages | 120 items, 32,277 Arabic words, 663 blocks | Automatic scores vs historical English; famous works |
| Systems on the same 120 | TranslateGemma 12B/27B official, Qwen-MT turbo, Gemini Flash-Lite, Gemini Flash | Matched-prompt bakeoff |
| Human diagnostic | 14 passages, two Arabic-first readers | Tail-risk exhibits, not a metric |
| Fable Round 1 | 50 new passages × 4 systems = 200 rows | Silver meaning-level flags; Arabic as truth; PD English omitted |
| Neural QE matrices | COMETKiwi item-level; MetricX item- and block-level | Synthetic corruptions; not a human gate |
| Cascade simulation | 50 passages, Lite vs Flash | Cost-aware routing sketch; **not** a production rate |

Sources in the 120: Baladhuri/Hitti, Ibn Khallikan/de Slane, Blunt, Ockley, Miskawayh/Margoliouth (7 trusted), Hariri/Chenery–Steingass (32 trusted). ATHAR English is in-copyright and is **not** in this evaluation. Public-domain English references **abridge** (Hitti retains about 40% of Arabic narrator markers); alignment quality and reference fidelity are different properties.

No model was trained. No invoices were pulled. No Gemini-batch dollar figure was produced.

---

## 3. Finding 1 — Standard metrics hide important failures

Fair chrF on the 115 items every system finished, scored against the same 19th-century PD English:

| system | chrF | leftover Arabic |
| --- | ---: | ---: |
| Gemini Flash | **47.06** | 0 |
| Gemini Flash-Lite | 45.80 | 0 |
| Qwen-MT turbo | 44.78 | 0 |
| TranslateGemma 27B official | 43.20 | 0 |
| TranslateGemma 12B official | 42.88 | 5 |

The ranking is real as a ranking. It is a poor picture of meaning.

Fable Round 1 asked a different question of 50 passages that were **not** in the 14-read: is there a publication-blocking error? `publishable = N` if and only if a closed flag fires (`TERM | ENTITY | ROLE | NUMBER | OMISSION | ADDITION | MISSING`).

| system | Round 1 publishable / 50 | Hard half (r1b) / 25 |
| --- | ---: | ---: |
| Gemini Flash | **48** | 24 |
| Gemini Flash-Lite | 23 | 11 |
| TranslateGemma 27B | 2 | 2 |
| Qwen-MT turbo | 0 | 0 |

chrF separated Flash from Qwen by about **four points**. Meaning-level flags on the hard half separated them **24 to 0**. Flash’s only hard-half N is an empty generation cell, not a bad translation.

chrF-vs-PD cannot be the quality ceiling. The references abridge; the metric rewards overlap with 19th-century English; and a four-point gap can conceal a categorical difference in whether a sitting is shippable.

---

## 4. Finding 2 — Completeness is not fidelity

Qwen-MT finished **120/120** items and **663/663** blocks with **zero leftover Arabic** and zero block errors. That was the operationally impressive number in the automatic table.

It is also the most misleading. Completeness is achieved by always committing — including committing to the wrong entity, the wrong agent, or an invented scene. On Round 1, Qwen is **0/50** publishable. The hard-half sitting is fluent throughout and wrong throughout: invented people inside Labid’s oryx hunt, a flintlock in Antara, asylum inverted so the fugitive grants it, magnanimity speeches flipped.

Gemini had empty-content failures on two verse/maqama blocks. Those failures are visible. Qwen’s failures are not. A factory that treats “finished, no Arabic left” as a safety signal will preferentially ship the most dangerous errors.

---

## 5. Finding 3 — Errors have structure

The failures are not generic bad prose. They cluster.

On the hard half, 63 of 100 rows were N. Flags on those rows: **TERM 60, ENTITY 26, ROLE 24, NUMBER 5, OMISSION 3, ADDITION 3, MISSING 2**. (A row may carry more than one flag.)

The 14-read exhibits are independently checkable:

- **Entity.** البريدي becomes “the postal service”; Luʾluʾ becomes “Pearl”; a mutiny becomes civil engineering.
- **Number.** سنة إحدى وتسعين ومائة is printed as 291 AH instead of 191.
- **Term.** نجوم المصادرات is recovered as installments, then the anaphor تلك النجوم becomes **stars**.
- **Role.** ʿUmar’s line is given to al-Nuʿmān; delayed news becomes sadness; a carpet-and-spear scene becomes a cavalry charge.
- **Addition.** Fluent verse with no Arabic anchor (Labid “fragrance…”).

Lite’s repeating signature is **local**: one confident false event in an otherwise clean row (a rare lemma, a homograph, a folio marker read as troop strength). TG and Qwen’s signature on this set is **global**: names, negations, and sajʿ collapse together.

That structure is why a flag layer is worth more than a scalar QE score, and why a glossary/extractor-judge might help Lite even if it cannot rescue Qwen.

Round-1 labels are silver. A blind regrade of 24 close calls agreed 20/24; all four flips were Y→N (first-pass leniency). They are a failure harvest, not a human benchmark.

---

## 6. Finding 4 — Current neural QE is not enough

We asked whether an existing quality-estimation model could be the publication gate. It cannot.

| setup | overall detection | terminology | negation | agent/patient |
| --- | ---: | ---: | ---: | ---: |
| COMETKiwi, item-level | 30.4% | ~0.8% | 10.9% | 9.1% |
| MetricX-24, item-level | 30.7% | (same blind spots) | 0% smoke / weak full | 0% smoke / weak full |
| MetricX-24, **block-level** | **63.4%** | **7.7%** | 32.6% | 40% (n=10) |

Block-level MetricX roughly doubled detection by making omission and addition visible, after structured blocks retired a truncation confound (37.5% of item-level inputs had exceeded the 1536-token window). That is a real engineering win.

It is still blind where this corpus fails: terminology substitution, negation, role reversal, and paragraph-structure collapse (0%). COMETKiwi is CC-BY-NC and cannot be required by shipping code. MetricX is Apache-2.0 and is the only shippable neural signal — as a **second opinion**, not the gate.

The publication gate remains: zero blocking flags, plus a small human audit. Deterministic checks (missing output, leftover Arabic, length, digits, glossary contradiction) are the first layer. They do not see sense errors. That is the job of an extractor-judge, which we have specified and not yet measured.

---

## 7. Finding 5 — Who is good at what

On this diagnostic set, not in general:

| system | Role now | Evidence |
| --- | --- | --- |
| **Gemini Flash** | Quality leader for a first corpus we would defend | 14-read A−; Round 1 48/50; hard half 24/25 |
| **Gemini Flash-Lite** | Interesting cheap first tier | 14-read B/B+; Round 1 23/50; failures often local |
| **Qwen-MT** | Out of production; kept as a failure-rich label source | 120/120 complete; Round 1 0/50 |
| **TranslateGemma 27B** | Open model we intend to **own and adapt**, not the current quality winner | 14-read C− with F-class tails; Round 1 2/50, both simple Ḥayy prose |

Flash won every card in the 14-read. That is **human judgment** on famous PD-paired works. It does **not** license “Gemini has general Classical Arabic competence.” Contamination is plausible. Excellent output can still be a remembered translation.

Raw TG 27B is not what we would publish as translations. Official 27B beat official 12B on composition in the 14-read; that decided the **owned serving model**, not the corpus producer. Do not fine-tune 12B on 27B. Do not distill Gemini API output into TranslateGemma until counsel clears the competitive-use clause.

Lite is the only mixed column in Round 1 (23 Y / 27 N). Flash is nearly all Y; TG and Qwen are nearly all N. A publishable-classifier trained on these 200 rows will learn **which model wrote the sentence**. If a learned router is trained later, it must be Arabic-side, on real factory gate outcomes, and only if it beats two if-statements on escaped blockers per dollar.

---

## 8. Implications

**Engineering.** Translate cheaply first where reasonable, verify the actual output, escalate failures. Source routing is a later cost optimization, not the product.

The sketch we can test: verse / sajʿ / metalinguistic text → Flash; otherwise Lite; cheap checks; if checks fail, **keep Lite and also fetch Flash**; ship Flash only if Flash’s own checks are clean; if both look dirty, queue a human. Errors are non-nested (Lite can pass where Flash fails).

Do not write that sketch as “46/50 publishable.” On the 50-passage silver simulation the implementable cascade did this:

- escaped blockers **4/50**
- human queue **14/50**
- verse/sajʿ sent to Flash **14/50**
- additional Flash escalations **10/50**

A 28% human queue is not yet a scalable factory. All-Flash on the same labels is 48/50 with 2 escaped — the quality ceiling, not the cost policy. Actual dollars, judge-call counts, and cost per Arabic word are **unmeasured**.

**Open model (hypothesis, not demonstrated).** Fable’s span-level diagnoses (wrong English, Arabic locus, suggested repair) are a more interesting supervision signal for TranslateGemma than generic synthetic translation. Failure-targeted corrections — named-entity protection, institutional vocabulary, negation, poetry routing — are a research hypothesis for Phase 2. We have not run that experiment.

---

## 9. What we do not know yet

1. **Does Flash/Lite’s ranking survive on genuinely unseen, untranslated Classical Arabic?** The 120 and the Fable 50 are famous PD-paired works. Blind-50 (no English in the pipeline, several works, several genres, several centuries, Arabic as the only grading source) is the test. Standardize the name: **Blind-50**, not blind-20.
2. **How accurately can a learned or LLM checker detect the semantic failure classes Fable identified?** Deterministic checks miss sense errors. Extractor-judge recall on TERM/ENTITY/ROLE is unknown.
3. **Can failure-targeted corrections materially improve TranslateGemma?** Hypothesis only. Do not distill Gemini matn into TG.
4. **What is the actual quality/cost frontier of cheap-first → verify → escalate?** Report escaped blockers, Flash calls, judge calls, human reviews, and billed cost per 100k Arabic words — not list-price extrapolations.

Those four questions are the principled basis for the next Fable schema. We do not yet know whether the next sitting should produce corrected translations, checker labels, router labels, or a human calibration of silver flags. Designing annotations before naming the question is how we over-collect.

---

## 10. Phase complete

**Phase 1 — Comparative evaluation and failure discovery — is complete.**

Outputs in hand: 120-passage evaluation set; multi-model translations; QE corruption experiments; human diagnostic reading; 200-row Fable silver failure corpus; closed flag taxonomy; initial cascade simulation.

**Phase 2 — Failure-aware translation — has not started.**

It should not start until another researcher can read this report and say: *I understand what they discovered, which claims are strong, which are preliminary, and why the next experiment follows.* The next experiment is whichever of the four questions above would change a decision. Likely Blind-50 before a book, and a bounded glossary test only if it is framed as “does Lite+glossary buy fewer Flash calls?” rather than as more research.

---

## 11. What can be shared, and what cannot

**Can be a public artifact (with a card):** the 120 Arabic passages and PD English refs; our model outputs with run metadata; alignment method; synthetic QE matrices; this report; the ledger; the 14-read notes; Round-1 silver flags clearly labelled silver and `train_eligible=false`.

**Cannot go public as gold or training data:** ATHAR English; Biruni 2001 Tehran print paired to Sachau page numbers; secrets.

We did not wait for a trained router or a perfect factory before writing this. The contribution worth talking about is a **failure-oriented evaluation methodology**, not a leaderboard and not a benchmark v1.0.

---

## Artifacts

| artifact | path |
| --- | --- |
| This report (markdown) | `~/versed-translator-data/RESEARCH_REPORT_2026-08-16.md` |
| Typeset v0.1 | `~/versed-translator-data/RESEARCH_REPORT_v0.1.pdf` |
| Ledger | repo `TRANSLATION_EXPERIMENTS.md` |
| Factory note | `~/versed-translator-data/FACTORY_V1.md` |
| 14-read | `~/versed-translator-data/benchmark-alignment/api_14_human_read.md` |
| Fable Round 1 | `~/versed-translator-data/benchmark-alignment/fable_r1/` |
| chrF scores | `~/versed-translator-data/benchmark-alignment/api_bakeoff_120_scores.json` |
