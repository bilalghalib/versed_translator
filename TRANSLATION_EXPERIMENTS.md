# TRANSLATION_EXPERIMENTS.md

Every benchmark, bakeoff, QE, throughput, and fine-tuning experiment gets an entry. Append-only; never rewrite a past entry — add a correction entry instead.

Entry template:

```
## EXP-YYYYMMDD-NN — <one-line name>
HYPOTHESIS:
SETUP:        (models + exact versions, prompt version, data version, hardware, seeds)
COST:         (predicted → actual)
RESULTS:      (tables/paths under the component's reports/ dir)
CONCLUSION:
DECISION FED: (which D* or component this informs)
```

---

## Imported prior findings (pre-repo, from `versed/alignment/RESEARCH.md`, 2026-03-26)

- **EXP-20260326-01 — Ihya register bakeoff:** GPT-5.4 few-shot (1 Ormsby exemplar) ≻ research-prompt dual-output ≻ zero-shot. One exemplar shifts register from generic to scholarly. Artifacts: `versed/tools/render_output/ghazali_comparison/`.
- **EXP-20260326-02 — GLM-5 feasibility:** strong Arabic quality (#2 SILMA) but paragraph-level inference infeasible on the free Modal endpoint (unbounded reasoning, 502s); sentence-level works and yields reusable philological analysis.
- **EXP-2026Q2-03 — DeepSeek/Gemma failure modes:** produced the fidelity rules now in `versed_core/derivatives/local_translation/prompts.py` (divine names, rasul≠nabi, no added honorifics, no summarization, preserve hedging). Merging analysis into translation calls degrades output.

These inform C2's prompt registry but do not substitute for the frozen-benchmark bakeoff.

---

## EXP-20260814-01 — COMETKiwi adversarial detection matrix (C4)

HYPOTHESIS: An existing QE system (COMETKiwi) can serve as the primary safety gate for classical-Arabic→English translation.
SETUP: `Unbabel/wmt22-cometkiwi-da` over 1,144 corrupted pairs built from run `20260813T233252Z-modal-translategemma_27b` (139 dev_bakeoff items, hadith-only). 13/15 master-plan injectors exercised; `alter_citation` + `collapse_paragraphs` not exercised (this slice has no verse citations or paragraph breaks). Threshold 0.02 on COMETKiwi's [0,1] scale.
COST: negligible (CPU, local).
RESULTS: `~/versed-translator-data/qe/tg27b-full/{detection_matrix.json,detection_matrix.md,scored_pairs.jsonl}`. Overall detection **30.4%**. `mistranslate_term` 0.8%, `reverse_agent_patient` 9.1%, `delete_negation` 10.9%, `remove_clause` 22.9% with a **negative** mean delta (−0.0041), `duplicate_sentence` 71.9%.
CONCLUSION: **Refuted.** Detection tracks fluency, not fidelity — the only well-detected corruption is a fluency artifact, and clause removal scores *better* than the complete translation. COMETKiwi cannot be the primary safety gate. It is also CC-BY-NC-SA, so it can never be required by shipping code.
DECISION FED: D4 (existing QE insufficient as primary gate), D4b (drove the two-mode research/shippable split), C5 (the 9 deterministic checks target exactly these blind spots).

## EXP-20260814-03 — TranslateGemma 12B leg + the prompt-label correction (C2/C3)

HYPOTHESIS: The 12B↔27B quality gap is small enough that 12B is the better serving choice.
SETUP: `google/translategemma-12b-it` (revision `d1b225e1…`), Modal H100, vLLM 0.11.0, bfloat16, same 139 dev_bakeoff items as the 27B and Claude legs. Ingested with the new `versed-harness ingest-modal` tool. Run once, no retries; sentinel `~/versed-translator-data/logs/done-tg12b` = 0.
COST: predicted ≤$0.2732 (the 27B figure) → actual **$0.1989**.
RESULTS:

| | TG 12B | TG 27B | Claude Sonnet 5 |
| --- | ---: | ---: | ---: |
| chrF | **49.857** | 50.239 | 50.599 |
| clean rows | 139/139 | 139/139 | 139/139 |
| wall incl. cold start | 181.3s | 249.0s | 3410s |
| GPU generation only | **44.2s** | 94.6s | n/a |
| est. cost | **$0.1989** | $0.2732 | n/a |
| mean latency/item | 0.317s | 0.680s | 24.5s |
| rows containing Arabic script | **0** | 2 | 3 |

Verification (the `wall_s: 0.06` false-success mode did not recur): error_count 0; two real chunks with 34.0s + 10.2s engine time and ~1240 output tok/s observed mid-run; output_tokens min 46 / median 274 / max 1024, sum 47,088 (vs 27B's 46,856), zero empty outputs; translations eyeballed as real fluent English.
CONCLUSION: **12B gives 99.24% of 27B's chrF (gap 0.38, 0.76% relative) for 2.14× less GPU time**, at 2.1× lower per-item latency, and is slightly *cleaner* on the untranslated-Arabic check. For serving economics this is close to decisive in 12B's favour. Caveat: hadith-only slice, single prompt, chrF only — a 0.38 chrF gap is within the range a genre-diverse benchmark could reorder.
⚠️ **CORRECTION TO PRIOR ENTRIES — prompt mislabel.** Both Modal legs (27B on 2026-08-13, 12B here) recorded `prompt_template_id: "v1"` in their run_meta. **That label is wrong.** `serve_translategemma.run_batch` hardcodes its own `DEFAULT_TEMPLATE` — a three-sentence instruction — and never touches `harness/prompts.py`. Harness `v1` is a much richer system prompt carrying the six fidelity rules from EXP-2026Q2-03, **including "Translate every clause. Do not summarize, compress, or silently drop material"** — the rule aimed at the exact omission failure C5's checks cannot detect. Consequences:
  1. **TG-vs-Claude is a prompt comparison as much as a model comparison**, and TranslateGemma was scored on the weaker prompt. Its near-parity (50.24 vs 50.60) is therefore an *understatement* of the model — which strengthens, not weakens, the D2a case for TranslateGemma.
  2. The **27B-vs-12B comparison above is clean** — both used the identical Modal template.
  3. Fixed so it cannot recur: the Modal template is registered as `modal_minimal_v1` in the prompt registry, `ingest-modal` requires an explicit `--template`, and `tests/test_prompts_modal_parity.py` pins the Modal literal to the registry entry and asserts it carries none of the fidelity rules.
  4. **The matched-prompt bakeoff has never been run.** Fold it into the single post-D1e measurement suite; do not spend a separate GPU run on it now.
DECISION FED: D2a (12B vs 27B; TranslateGemma understated vs Claude), D3a (serving config — 12B is the economics favourite), D2b/D3b (cost actuals: $0.20/139 items).

## EXP-20260814-02 — MetricX-24 as a shippable second QE opinion (C4)

HYPOTHESIS: MetricX-QE is (a) permissively licensed enough to ship, and (b) covers COMETKiwi's fidelity blind spots.
SETUP: `google/metricx-24-hybrid-large-v2p6` (apache-2.0, ungated) + `google/mt5-large` tokenizer, reference-free mode, CPU. Input `"source: {src} candidate: {hyp}"`, `max_length=1536`, EOS stripped after truncation (MetricX trained in T5X without EOS). Score is error on [0,25], lower better → **negated inside the scorer closure** so the engine's higher-is-better contract holds. Threshold 0.5 (= 2% of scale, matching COMETKiwi's 0.02/[0,1]; independently ≈ half an MQM minor error).
COST: negligible (CPU, local). ~6.2 s/segment.
RESULTS (**SMOKE ONLY — 20 items / 162 pairs / 324 segments**): `~/versed-translator-data/qe/tg27b-smoke20-metricx/`. Overall detection 33.3%. Score range [−20.17, −1.68] over 139 distinct values (not constant — plausibility check passes). Beats COMETKiwi on `omit_person` (0.65 vs 0.30), `leave_arabic_untranslated` (0.60 vs 0.35), `remove_clause` (0.53 vs 0.23), `hallucinate_prose` (0.55 vs 0.42). **Shares the same critical blind spots: `delete_negation` 0.0, `mistranslate_term` 0.0, `reverse_agent_patient` 0.0.** Full 1,144-pair run launched detached 2026-08-14 12:36 (~3.8h; sentinel `~/versed-translator-data/logs/done-metricx-full`).
⚠️ CONFOUND: **126/324 inputs (39%) hit the 1536-token cap.** Truncated inputs show median clean error 17.51 vs 8.88 for inputs that fit — truncation roughly doubles apparent error, and it eats the END of the input, i.e. the candidate being judged. Length-increasing injectors are truncated more than their clean counterparts, biasing deltas toward zero. The `duplicate_sentence` row (−1.49 mean delta, 5%) is an **artifact of the cap, not a property of MetricX**. Instrumented, not fixed: the scorer counts truncations and the runner stamps `truncated_inputs`/`truncated_fraction` into the summary. → D4c.
CONCLUSION (partial, pending the full run): (a) **confirmed** — apache-2.0 and ungated, the first reference-free QE model here that shipping code may require; (b) **refuted** — MetricX misses negation deletion, terminology substitution, and agent/patient reversal as completely as COMETKiwi does. Two independent neural QE systems failing on the same three highest-severity fidelity errors is much stronger evidence for the deterministic-check ensemble than one was.
CAVEATS: smoke-scale n; hadith-only slice; the 39% truncation confound above; MetricX has never seen isnad chains or honorifics, so the median 8.88 error on *clean* 27B output may be domain mismatch rather than a quality signal — undetermined without human labels.
DECISION FED: D4b (shippable mode has a viable neural signal), D4c (token-window handling), C5 (deterministic checks remain load-bearing, not a stopgap).

## EXP-20260814-04 — Baladhuri/Hitti passage alignment + human spot audit (C1)

HYPOTHESIS: Targeted passage alignment from PD translations can supply genre coverage at benchmark scale without waiting for the C7 alignment engine (D1e option d).
SETUP: OpenITI `0279Baladhuri.FutuhBuldan` (genre `التاريخ` from `021.BookSUBJ`) against Hitti's 1916 *Origins of the Islamic State* vol. 1. Anchors: transliterated transmitter names matched on both sides, so a passage bracketed by a matched name at each end cannot be off-by-one. 90 Arabic sections → 39 confirmed section↔chapter pairs → 199 khabar cuts → 109 assembled → **39 selected** (30 in the 100–250 band, 9 in 250–600, across 20 chapters). Method split 21 structural / 18 llm_proposed; confidence capped at 0.85 for LLM-only agreement.
COST: negligible (local + a small LLM adjudication pass).
RESULTS: **Human spot audit 15/15 aligned** (Bilal, LLM-assisted, report-level criterion), covering 15 distinct chapters. **No hidden one-report shift in any of the 15** — the defect that reads plausibly row-by-row and that word-ratio checks miss. Agent's own estimate for the shipped set was ~90% fully parallel with the residual being partial overlap, not shift; the audit is consistent with that.
⚠️ SECOND FINDING (arguably the more important one): **the reference itself abridges.** Hitti renders only **40%** of the Arabic narrator markers — 102 English reporting verbs vs 257 Arabic `قال/حدثنا/حدثني/أخبر../يقول` — with 24/39 passages losing some. This is Hitti's stated policy (isnads abridged to first + last authority), not an alignment defect. It collides with C4/C5: chrF against an abridging reference would penalise a model that faithfully translates `قال`, rewarding the exact omission behaviour the project has established as most dangerous and least detectable. Every item now carries `reference_fidelity`, `scaffolding_ar/en`, `scaffolding_retained`, and a `narrator_scaffolding_dropped:N` flag.
CONCLUSION: Option (d) works. **Alignment quality and reference fidelity are two separate properties and must be measured separately** — a pair can be perfectly aligned and still be an abridged translation. Yield says one work gives ~30 passages in 100–250 but only ~9 in 250–600, so **closing the long-band gap needs 3–4 PD works, not one**. OCR apparatus, not alignment, is the quality ceiling (13/109 carry a footnote fused mid-sentence; flagged and excluded rather than excised).
CAVEATS: one work, one translator, one genre. The 40% scaffolding ratio is translator-specific and tells us nothing about de Slane or Chenery — re-measure per work. 15 audited of 39 shipped; the ~100-item target (C1 checkpoint 3) is not met.
DECISION FED: D1e (option d validated), C1 checkpoint 3 (first tranche), C8 (exclude these from isnad training signal), C2 scoring (report isnad fidelity separately from chrF).

## EXP-20260814-05 — MetricX-24 full detection matrix (C4) — completes EXP-20260814-02

HYPOTHESIS: (update at full scale) MetricX-QE covers COMETKiwi's fidelity blind spots.
SETUP: identical to EXP-20260814-02 but the **full 1,144 pairs**, 13/15 injectors, threshold 0.5 on the negated [-25,0] scale. Ran detached; sentinel `done-metricx-full` = 0.
RESULTS: `~/versed-translator-data/qe/tg27b-full-metricx/`. Plausibility checks pass — score range [−22.16, −1.67] over **962 distinct values** (not constant), 1,144 pairs scored.

| injector | severity | n | COMETKiwi | MetricX |
| --- | --- | ---: | ---: | ---: |
| reverse_agent_patient | critical | 11 | 0.091 | **0.000** |
| mistranslate_term | major | 120 | 0.008 | **0.008** |
| delete_negation | critical | 92 | 0.109 | **0.098** |
| remove_isnad_narrator | critical | 127 | 0.228 | 0.252 |
| remove_clause | critical | 105 | 0.229 | **0.333** |
| omit_quotation | critical | 131 | 0.275 | **0.405** |
| duplicate_sentence | moderate | 139 | **0.719** | 0.065 |
| **OVERALL** | | 1144 | **0.304** | **0.307** |

CONCLUSION: **Two independently-trained QE systems, from different labs, on different scales, agree to within 0.3 points overall (30.4% vs 30.7%) — and are blind to the same three critical errors.** Agent/patient reversal 9%→**0%**, terminology substitution ~1% in both, negation deletion ~10% in both. That convergence is much stronger evidence than either result alone: it is not a quirk of one model's training, it is what reference-free neural QE does not measure. **The C5 deterministic ensemble is therefore load-bearing, not a stopgap**, and no amount of swapping neural QE models will fix it.
Where they differ, MetricX is better on omission-type errors (`remove_clause` 0.333 vs 0.229, `omit_quotation` 0.405 vs 0.275) — which matters, since omission is our highest-severity failure. Combined with its apache-2.0 licence (vs COMETKiwi's CC-BY-NC-SA), **MetricX is the better choice for the shippable mode on both counts.**
⚠️ `duplicate_sentence` 0.065 with a **negative** mean delta (−1.36) is the known truncation artifact, not a property of MetricX: **37.5% of inputs (859) exceeded the 1536-token window**, confirming the smoke's 39%. Length-increasing corruptions truncate more than their clean counterparts. D2e/D4c (structured blocks) removes this.
CAVEATS: hadith-only slice; `alter_date`/`change_number` have n=1 each so their 0% is directional only; thresholds (0.02 vs 0.5) are scale-matched by proportion, not calibrated against human judgments — C5 checkpoint 2 must do that.
DECISION FED: D4 (settled — existing QE cannot be the primary gate), D4b (shippable mode: MetricX, apache-2.0, better on omission), C5 (deterministic checks confirmed load-bearing), D2e/D4c (truncation confirmed at full scale).

## EXP-20260814-06 — Structured blocks implemented: truncation 37.5% → 0.7% (D2e/D4c)

HYPOTHESIS: Translating in ID-bearing blocks retires two separately-measured failures at once — (a) a dropped block is countable where a dropped clause is invisible, (b) short blocks stay inside MetricX's 1536-token window.
SETUP: `harness.blocks` segments on sentence then clause punctuation, packing to an *evened* budget of ≤60 Arabic words; block id = `<item_id>#bNNNN`. Applied to the same 139 `dev_bakeoff` items → **522 blocks** (mean 3.76/item, median 3, max 14; mean 43.3 words, median 48). 60 words was sized from the measured mT5 tokenization of this slice: diacritized classical Arabic runs **5.84 mT5 tokens/word** (max 7.3), so an item's median source alone is 710 tokens and its max 3,851 — the whole cause of the 37.5% truncation. Translation: `google/translategemma-12b-it` (revision `d1b225e1…`), Modal H100, vLLM 0.11.0, bfloat16, temperature 0.1, max_new_tokens 1536, one detached run, sentinel `done-tg12b-blocks` = 0.
COST: predicted ≤$1.00 hard stop, ≤$0.30 expected (the 12B item-level leg was $0.1989) → **actual $0.1753** (159.8s wall incl. cold start). Plus ~$0.001 of DeepSeek API for the structured-contract leg below.
RESULTS:

**(1) The truncation claim — measured, and validated against the known baseline.** Computed through the project's own `metricx_qe_input` + `metricx_encode`, which **reproduces the published `truncated_fraction: 0.3754` exactly** on the 27B item-level run before being applied to blocks:

| | pairs | segments | truncated | **truncated_fraction** | median seg tokens | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| item-level TG27B (published baseline) | 1,144 | 2,288 | 859 | **0.3754** | 1,085 | 5,150 |
| item-level TG12B (same model, free-form) | 1,166 | 2,332 | 895 | 0.3838 | 1,110 | 4,999 |
| **block-level TG12B (D2e)** | 3,235 | 6,470 | 47 | **0.0073** | **394** | 4,032 |

**A 51× reduction, and it is better than it looks: all 47 truncations trace to exactly 3 of 522 blocks** (see (3)), which the fix committed alongside this entry now reports as errors. With those excluded the block-level figure is **0.0000**. Median QE input falls 1,085 → 394 tokens; nothing else in the study changed.

**(2) ID loss became a counted error, and immediately caught a real one.** A 40-block structured leg through `deepseek-chat` (`--adapter openai_compat`, template `structured_blocks_v1`): 39 clean, and **1 block (2.5%) silently dropped by the model**, surfaced as `id_missing_from_structured_response` with `id_loss_count: 1`, `id_preservation_rate: 0.975` in `run_meta.json`. On the free-text path that block would have been an unremarkably shorter passage — the exact failure COMETKiwi scores *higher* (22.9%, negative mean delta) and MetricX catches 33.3% of the time. This is the D2e claim demonstrated rather than argued.

**(3) Quality cost of blocking, honestly separated.** chrF against `reference_english`, same 139 items, same model:

| | chrF (139) | chrF (136, excl. the 3 degenerate items) | rows containing Arabic |
| --- | ---: | ---: | ---: |
| free-form item-level | **49.857** | 49.983 | 0 |
| block-level, reassembled | 48.817 | 49.335 | 3 |

So **blocking itself costs −0.65 chrF (−1.3% relative)** — context lost across block boundaries — and a further −0.52 comes from three generations that derailed. That −0.65 is the real price of the contract on this slice, and it is the number to re-check on non-hadith genres.

⚠️ **FINDING — TranslateGemma's chat template is not a general chat API.** The structured JSON probe failed on the first GPU call with `TemplateError: User role must provide 'content' as an iterable with exactly one item... mapping(type:'text'|'image', source_lang_code, target_lang_code, text, image)`. `translategemma-12b-it` is fine-tuned behind a fixed translation API, so a plain `{"role":"user","content":"<json>"}` is rejected *by the template*, before the model sees anything. The run therefore fell back — by design, once, recorded — to `modal_minimal_v1` at one block per prompt, which still gives ID-preserving blocks (one prompt in, one translation out) and is what produced every number above. **Whether TranslateGemma can hold the JSON contract remains unmeasured**; the failure was our message shape, not its capability, and the handler now degrades to a raw completion prompt instead of erroring. The contract itself is proven on a general instruct model in (2).

⚠️ **FINDING — 3/522 blocks (0.6%) degenerated into repetition loops** and ran to the 1536-token cap, two in English (`"And he narrated..."` ×N), one flipping into Arabic. Same shape as the Sonnet 5 `max_tokens` trap: the text is real up to the point it derails, so nothing flagged it — `n_ok` said 522/522. Fixed: `finish_reason == "length"` is now the named error `max_new_tokens_truncated` and the sampling config is written to the run summary. These three rows are the *entire* source of the residual block-level truncation and of all 3 Arabic-bearing rows.

Verification (the `wall_s: 0.06` false-success mode did not recur): error_count 0 with real per-slice engine times (7.2s / 23.8s / 7.4s / 7.4s / 1.8s across five 128-prompt slices); output_tokens min 12 / median 101.5 / max 1536, sum 54,337; zero empty outputs; translations read as real English and were spot-read at four random block ids; `prompt_template_id` verified against the code path that ran (the summary records the label the builder returned, and the log shows the probe failing and the fallback engaging).
CONCLUSION: **D2e/D4c delivered on both counts.** Truncation is retired (0.3754 → 0.0073, and 0.0000 once capped generations are errors), which un-confounds every length-increasing injector in the C4 matrix; and ID loss is now a first-class run-level metric that caught a live 2.5% omission on its first real use. The cost is −0.65 chrF on hadith. The block-level MetricX detection matrix is running detached (6,470 segments; log `metricx-blocks.log`, sentinel `done-metricx-blocks`, ETA 7.4–9.2h) — it will say whether short blocks also move the *detection* rates, which this entry does not claim. ⚠️ Unexpected cost fact: **MetricX CPU time scales sub-linearly with input length, so blocks cost ~2× more in total.** In-flight marginal rates **4.1–5.1 s/segment** on 394-token block inputs vs the completed item-level study's **7.24 s/segment** on 1,085-token inputs: a 2.83× shorter input buys only **29–43%** less time per segment, while blocking multiplies segment *count* by 2.83×. Net **1.6–2.0×** (7.4–9.2h vs 4.6h). **Blocks make QE more accurate and roughly twice as expensive at once** — the opposite of the intuition the design was chosen on, and the concrete argument for moving QE to Modal before the benchmark grows.
⚠️ **Quoted as a range on purpose, and the reason is a reusable methodology lesson.** Three successive estimates in one session read 5.5, 4.2 and 5.4 s/segment, each looking authoritative, and two of them were written into this ledger before being corrected. Causes: (a) the *gross* rate (wall ÷ segments) includes the one-off model load and therefore drifts downward through a run — 5.65 → 5.38 → 4.97 across samples — so it is not a stable estimator early; use the marginal rate between samples. (b) The sampling machine was concurrently running this session's tests, so every in-flight figure is an **upper bound on a quiet machine**. **Do not re-derive this from a partial log: the exact number is `scoring_seconds` in the finished `detection_matrix.json`.**
⚠️ **SEGMENTER VERSION — the artifact of record is the block file, not the segmenter.** Everything above was measured on `dev_bakeoff_blocks60.jsonl` as generated on 2026-08-14, **522 blocks**. A packing bug found in review immediately afterwards (evening the block size derived its target from `total/max_words`, which under-counts capacity because punctuation pieces are indivisible, so three 30-word sentences plus a 10-word one became 3 blocks instead of 2) was fixed in the same session. **The fixed segmenter yields 496 blocks on the same input** — 5% fewer calls, and no block under 9 words (was 2). Block *lengths* barely move (median 48 → 50 words, max still 60), so the truncation and chrF results are unaffected in substance; only the exact block ids differ. The 522-block file is kept as the artifact the measurement was run on, and `tests/test_blocks.py::test_segmentation_of_the_real_slice_is_stable` now pins the count so this cannot drift unnoticed again. **Re-running `versed-harness blocks` today will NOT reproduce the 522-block file** — use the committed file to re-derive any number in this entry.
CAVEATS: hadith-only slice; 60 words is sized from this slice's tokenization and should be re-derived per genre; the −0.65 chrF is measured against an abridging-reference corpus (see EXP-20260814-04) and one prompt; the structured JSON path is proven on DeepSeek, not on the serving model.
DECISION FED: **D2e** (implemented — structured blocks are the harness default and ID loss is a run metric), **D4c** (settled — the token window is dissolved by blocks, not by chunking or a longer-context model), C5 (the clause-removal known gap should now be re-scoped: a dropped *block* is observable), D2a/D3a (block-level serving costs $0.1753/139 items at 12B).

## EXP-20260815-01 — Independent blind re-audit of the selected set; ATHAR rights verified at the edition level

HYPOTHESIS: (triggered by a false alarm) Bilal read an alignment `review.html` and concluded "the arabic and english don't match at all." Either the aligner is broken, or the page was showing its own reject pile.
SETUP: 15-agent audit, 2026-08-15. Nine bilingual auditors re-judged **all 81 selected passages**, blinded to stored `llm_verdict`s, required to cite name/number/image-level evidence at the start, end, and 2–3 middle probes of every pair, and to check for systematic one-off shift per batch. Two auditors re-judged **24 rejects** sampled evenly (12 Ockley, 12 Ibn Khallikan) against their stored verdicts. One agent verified ATHAR licensing against the HF card, arXiv 2407.19835, rasaif.com, and published translation editions.
RESULTS:

| source | aligned | partial | misaligned | partials are |
| --- | ---: | ---: | ---: | --- |
| baladhuri_hitti | 37 | 2 | 0 | one extra English report trailing at the end |
| ibn_khallikan_deslane | 21 | 0 | 0 | — |
| blunt_odes | 13 | 1 | 0 | ~3 extra couplets past the Arabic end |
| ockley_hayy | 2 | 5 | 0 | ±1 sentence jitter at chunk boundaries |
| **total** | **73** | **8** | **0** | |

No systematic one-report shift in any source. Two mechanical defect patterns: **Ockley boundary jitter** (the length proposer's chunk edges drift one sentence; a passage's final Arabic sentence lands at the start of the next English chunk) and **Blunt hemistich smear** (English sliced by line count, so every internal boundary carries half a verse of its neighbour, same direction each time). Rejects: **24/24 genuinely bad, 0 would have been accepted** — Ockley rejects show phase drift ~half a segment; Ibn Khallikan rejects all start correctly and overshoot the end (1 to dozens of extra biographies, ratios 2.5×–150×; 77/86 were ratio-rejected before ever reaching the LLM).
The alarm's cause: `review.html` shows all proposals **worst-first including rejects** (Ockley page opens on a conf-0.15, misaligned-0.97 pair). The selected-only `review_shipping.html` existed only for Baladhuri — same scare, same fix, never propagated.
**ATHAR (verified at the edition level):** English rows match published in-copyright translations verbatim — Muqaddimah = Rosenthal (Princeton 1958, renewed 1986, in print), Book of Idols = Faris (Princeton 1952); Tabari, Book of Revenue, Unique Necklace, and The Optics have **no PD English translation in existence**; ~3/4 of the 66,043 pairs ride on in-copyright English, ≤~13% plausibly US-PD (Nishwar/Margoliouth 1922, Canon/Gruner 1930, contingent on edition checks). The paper's "created by human volunteers" claim (§3.2) is contradicted by the verbatim matches; its scraping-permission footnote addresses site terms, not copyright. The HF card's own labels conflict (YAML `cc-by-sa-4.0` vs prose CC BY-NC 4.0) and **both are ineffective — you cannot license what you don't own**. rasaif.com now 301-redirects to a successor corpus whose page disclaims all rights over the translations. Re-scraping rasaif therefore changes nothing.
CONCLUSION: **The aligner and its filter both hold.** Zero misaligned passages shipped; zero over-rejection observed; the defect budget is 8 edge-jitter partials traceable to two mechanical causes, fixable or trimmable at freeze. The false alarm was a review-surface problem, now a standing trap + rule (humans review shipping views only). ATHAR is confirmed **eval_internal forever**; the PD-alignment path is not compliance overhead — it is the only way a public benchmark with English references can exist, which makes the benchmark itself a novel, publishable artifact.
CAVEATS: auditors were LLM agents (blinded, evidence-cited) — corroborated by, not a substitute for, the 15/15 human audit on Baladhuri; the standing ask to spot-check ~10–15 pairs per new source on shipping pages stands. ATHAR verbatim matches were sampled per work, not exhaustive row-by-row; renewal-record checks (Faris 1952, Khadduri 1961) not run.
DECISION FED: review-surface rule (traps), contamination-clean clause added to the v0.1 stop condition, blast-radius model-routing rule (traps), C8 A/B/C experiment parked as a GitHub issue, "Isnād Corpus" recorded as a D12a naming candidate. Source: 2026-08-15 session; full agent returns in that session's scratchpad `audit.json`.

## EXP-20260815-02 — Miskawayh / Margoliouth year-anchored driver (C1)

HYPOTHESIS: Hijri-year headings are a real bilateral anchor for *Tajarib al-Umam* / *Eclipse of the 'Abbasid Caliphate*, but within-year cuts are proposals (English running head lags a page) and will not survive content adjudication at the 25–40% rate seen on name-bracketed sources unless adjudication is mandatory.
SETUP: OpenITI `0421Miskawayh.Tajarib` against Margoliouth & Amedroz 1921 vols IV–V (`eclipse_04ameduoft`, `eclipse_05ameduoft`). Extractor `sources/miskawayh.py` (year blocks + name-refined proportional cuts); new driver `benchmark/miskawayh_alignment.py`. Seed `20260815`. Adjudicator `claude-sonnet-5`, `--adjudicate-limit 120` year-spread of 340 eligible (bands 100–600, ratio 0.75–3.2, no `page_markers_nonmonotone`). Selection requires `aligned` verdict, spreads across years, target 40. Sentinel `~/versed-translator-data/benchmark-alignment/miskawayh_eclipse/done-adjudicate` = 0.
COST: 120 Sonnet 5 calls; cache at `llm_verdicts.json` (replayable).
RESULTS: 71 Arabic years / 73 English years → 69 shared → 59 used / 10 rejected on ratio → **504 proposals** (340 eligible). Adjudication of 120:

| verdict | n | share |
| --- | ---: | ---: |
| aligned | 24 | 20% |
| partial | 84 | 70% |
| misaligned | 12 | 10% |

**24 selected** (15 in 100–250, 9 in 250–600, 22 years, method `llm_proposed`, confidence 0.71–0.825). Shipping page: `~/versed-translator-data/benchmark-alignment/miskawayh_eclipse/review_shipping.html`. Manifest: `benchmark/alignment/miskawayh_eclipse/`.
CONCLUSION: **The year anchor works as a coarse unit; the within-year cut does not, and the adjudicator says so honestly.** 20% aligned is below the 25–40% seen on name-bracketed sources, and the 70% partial mass is exactly the running-head lag the extractor documented. Nothing unadjudicated shipped. History (`التاريخ`) is already over the v0.1 40% cap, so **do not run another Miskawayh round and skip Suyuti for now** — the take is the 9 long-band passages pending human shipping review. Next source must be a new genre (Hariri / maqama).
CAVEATS: 120/340 judged, not all proposals; human shipping review not yet done (standing 10–15 spot-check); `reference_fidelity` is `pending_human_audit`; Margoliouth abridgement not measured the way Hitti's 40% narrator drop was.
DECISION FED: C1 diversification (long band +24 pending review), freeze-bar genre cap (stop mining history), review-surface rule (`render_shipping_page` now shared; every driver emits both pages).

## EXP-20260815-03 — Hariri / Chenery–Steingass maqama-anchored driver (C1)

HYPOTHESIS: The fifty maqamat are a real bilateral unit (Arabic headings; English `THE NTH ASSEMBLY`), so sequence pairing is an anchor, but interior cuts have no second bracket and Chenery/Steingass may abridge, gloss, or prepend a synopsis — adjudication will be mandatory and yield should beat Miskawayh's 20% because the unit is discrete rather than a year-block with page-lag.
SETUP: OpenITI `0516IbnCaliHariri.Maqamat` (PRIMARY_VERSION JK009202) against archive.org `the-assembly-of-al-hariri-all-50` (`The_Assembly_of_Al_Hariri_All_50_djvu.txt`). Pair by document sequence 1–50, never by printed Arabic numerals (dirty in this witness). Extractor drops running heads and the Chenery/Steingass synopsis that sits between the heading and `Al Harith, son of Hammam, related` (assembly 33 has no formula and falls back to dropping `In this Assembly…`). Driver `benchmark/hariri_alignment.py`. Seed `20260815`. Adjudicator `claude-sonnet-5`, all 103 eligible (bands 100–600, ratio 0.75–3.2). Selection requires `aligned`, spreads across maqama numbers, target 40. Rights `PD_US_PRE_1930_PUBLICATION` (Chenery 1867 / Steingass 1898). Sentinel `~/versed-translator-data/benchmark-alignment/hariri_assemblies/done-adjudicate` = 0.
COST: 103 Sonnet 5 calls (~9 min); cache at `llm_verdicts.json` (replayable). 0 errors.
RESULTS: 50 Arabic maqamat / 50 English assemblies → 50 paired → 47 used / 3 rejected on ratio (21, 26, 44) → **132 proposals** (103 eligible). Adjudication of 103:

| verdict | n | share |
| --- | ---: | ---: |
| aligned | 51 | 50% |
| partial | 52 | 50% |
| misaligned | 0 | 0% |
| error | 0 | 0% |

**37 selected** (17 in 100–250, 20 in 250–600, 26 maqamat, method `llm_proposed`, confidence 0.675–0.825). Short band only had 17 aligned, so the 40-target undershot honestly. Shipping page: `~/versed-translator-data/benchmark-alignment/hariri_assemblies/review_shipping.html`. Manifest: `benchmark/alignment/hariri_assemblies/`.
CONCLUSION: **The maqama is a working bilateral anchor, and dropping the English synopsis was load-bearing.** 50% aligned is in the name-bracketed 25–40%+ band and twice Miskawayh; zero misaligned among 103 is the tell that sequence pairing held. The 50% partial mass is interior-cut jitter (verse islands, remaining running-head OCR), caught rather than shipped. Adab/maqama is filled. **Do not run another Hariri round.** Next empty high-value genre is kalam/falsafa (Ibn Rushd), not more adab.
CAVEATS: human shipping review not yet done (standing 10–15 spot-check); `reference_fidelity` is `pending_human_audit`; PD_TRANSLATIONS called the all-50 scan "notes-free" — true of footnotes, false of the per-maqama synopses, which the extractor now strips; 3 maqamat dropped on ratio rather than forced; printed Arabic numerals remain untrusted.
DECISION FED: C1 diversification (adab/maqama +37 pending review), freeze-bar genre coverage (history still over cap until these ship; do not mine more adab next).

## EXP-20260815-04 — MetricX-24 block-level detection matrix (C4) — completes EXP-20260814-06's in-flight QE rerun

HYPOTHESIS: Scoring MetricX on ID-bearing blocks (truncation retired) raises detection of omission/addition relative to the item-level matrix, without making neural QE a safety gate for terminology, negation, or agent/patient reversal.
SETUP: `google/metricx-24-hybrid-large-v2p6` + `google/mt5-large` tokenizer, reference-free, CPU, same negated-error contract and threshold 0.5 as EXP-20260814-02/05. Input run `20260814T183238Z-modal-translategemma_12b-blocks` (522 blocks from the 139 `dev_bakeoff` items; the 522-block file of record, not today's 496-block segmenter). Sentinel `~/versed-translator-data/logs/done-metricx-blocks` = 0.
COST: CPU, local. EXP-20260814-06's in-flight bound was 7.4–9.2 h at 4.1–5.1 s/segment → actual **`scoring_seconds`: 19,449.2 (5.40 h, 3.01 s/segment over 6,470 segments)**. Item-level MetricX was 16,574 s / 7.24 s/segment; net wall is 1.17× that study (the 1.6–2.0× figure was a busy-machine upper bound). Sub-linear scaling holds: 2.83× more segments, 2.4× less time each.
RESULTS: `~/versed-translator-data/qe/tg12b-blocks-metricx/{detection_matrix.json,detection_matrix.md,scored_pairs.jsonl}`. **Full block run, not smoke** — 3,235 pairs (jsonl line count matches), 14/15 injectors (`collapse_paragraphs` now fires, n=35; only `alter_citation` unexercised). Plausibility: score range [−25.0, −0.746] over **3,955 distinct values** (floor hit is the three repetition-loop blocks from EXP-20260814-06; not a constant-score failure). `truncated_inputs` 47 / `truncated_fraction` **0.0073** — identical to the EXP-20260814-06 token-count preview.

n is this run; item-level columns are EXP-20260814-01/05 rates (1,144 pairs, 13/15 injectors).

| injector | severity | n | COMETKiwi item | MetricX item | **MetricX blocks** |
| --- | --- | ---: | ---: | ---: | ---: |
| mistranslate_term | major | 246 | 0.008 | 0.008 | **0.077** |
| delete_negation | critical | 172 | 0.109 | 0.098 | **0.326** |
| reverse_agent_patient | critical | 10 | 0.091 | 0.000 | **0.400** |
| collapse_paragraphs | moderate | 35 | — | — | **0.000** |
| certainty_inflation | major | 7 | 0.000 | 0.200 | **0.000** |
| duplicate_sentence | moderate | 522 | 0.719 | 0.065 | 0.375 |
| remove_clause | critical | 356 | 0.229 | 0.333 | **0.587** |
| remove_isnad_narrator | critical | 164 | 0.228 | 0.252 | **0.677** |
| omit_quotation | critical | 444 | 0.275 | 0.405 | **0.754** |
| leave_arabic_untranslated | major | 522 | 0.353 | 0.532 | **0.812** |
| omit_person | major | 233 | 0.299 | 0.500 | **0.867** |
| hallucinate_prose | major | 522 | 0.417 | 0.504 | **0.944** |
| **OVERALL** | | **3235** | **0.304** | **0.307** | **0.634** |

Omission/addition detection rises with the shorter unit: `remove_clause` 0.333→0.587, `omit_quotation` 0.405→0.754, `omit_person` 0.500→0.867, `leave_arabic_untranslated` 0.532→0.812, `hallucinate_prose` 0.504→0.944, `remove_isnad_narrator` 0.252→0.677. A dropped or added span is a larger fraction of a ~43-word block than of a whole item, and length-changing injectors are no longer eaten by the 1536-token cap.
⚠️ Truncation **no longer confounds** this matrix. Residual 0.73% is the three `max_new_tokens_truncated` generations already named in EXP-20260814-06; excluding them is 0.0000. `duplicate_sentence` still has a **negative** mean delta (−0.93) at 37.5% detection — with the cap gone, that row is a MetricX fluency bias, not a truncation artifact. The item-level 0.065 / −1.36 figure stays retracted.
⚠️ `collapse_paragraphs` is **0% with mean/median/min/max delta all 0.0** (n=35): MetricX is invariant to paragraph breaks. That is a C5 structure-check finding, not a QE miss to wait out.
CONCLUSION: **Blocks roughly double MetricX's overall detection (30.7% → 63.4%) by making omission and addition visible, but neural QE is still not the safety gate** — terminology 7.7%, negation 32.6%, agent/patient reversal 40% (n=10) remain weak, and `collapse_paragraphs` is a hard zero.
CAVEATS: hadith-only; comparison is 12B-blocks vs 27B-item (no 12B item-level MetricX matrix exists, so blocking and model are not fully isolated — the 12B↔27B chrF gap was 0.38, so the 2× detection lift is not that gap); `reverse_agent_patient` n=10 and `alter_date`/`change_number` n=1 are directional; thresholds still uncalibrated against human labels.
DECISION FED: C4 (block-level matrix complete), C5 (deterministic checks remain load-bearing: terminology, negation, agent/patient, and paragraph structure), D4 (existing QE still cannot be the primary gate), D4c (truncation confound retired in the scored matrix, not only the token preview).

## EXP-20260815-05 — Ibn Rushd / Jamil-ur-Rehman treatise-anchored driver (C1)

HYPOTHESIS: Fasl al-Maqal + Damima + Kashf against Jamil-ur-Rehman 1921 (Gutenberg #65708) can fill the empty kalam/falsafa genre via treatise-level pairing, with interior cuts as proposals.
SETUP: OpenITI `0595IbnRushdHafid.FaslMaqal` PRIMARY_VERSION `JK010686` against Gutenberg #65708 (`pg65708_philosophy_theology_averroes.txt`). Driver `benchmark/ibn_rushd_alignment.py`. Seed `20260815`. Adjudicator `claude-sonnet-5`, all 22 eligible. Selection requires `aligned`. Rights `PD_US_PRE_1930_PUBLICATION` (Baroda 1-1-1921 title page). Sentinel `~/versed-translator-data/benchmark-alignment/ibn_rushd_rehman/done-adjudicate` = 0.
COST: 22 Sonnet 5 calls; cache at `llm_verdicts.json`. 0 errors.
RESULTS: OpenITI witness is **Fasl + Damima only**; English Kashf (~39k words) unpaired, not cut. 2 Arabic / 3 English treatises → 2 paired → 25 proposals (22 eligible). Adjudication of 22:

| verdict | n | share |
| --- | ---: | ---: |
| aligned | 2 | 9% |
| partial | 20 | 91% |
| misaligned | 0 | 0% |
| error | 0 | 0% |

**2 selected** (1 in 100–250, 1 in 250–600). Damima opener aligned; almost every interior cut is extra English at the start plus omitted Arabic at the end — Ockley-family smear. Shipping page: `~/versed-translator-data/benchmark-alignment/ibn_rushd_rehman/review_shipping.html`. Manifest: `benchmark/alignment/ibn_rushd_rehman/`.
CONCLUSION: **Treatise pairing is real; interior length cuts are not, and this does not fill kalam/falsafa.** 9% aligned is below even Miskawayh's 20%. **Do not run another length pass.** Retry only with embeddings, or leave the source and cut Usama/Biruni instead. Kashf stays unpaired until an Arabic witness exists.
CAVEATS: n=22 is the whole eligible pool, not a sample; human review of 2 pairs is optional and does not make a genre; catalog "partial" OpenITI flag was correct.
DECISION FED: C1 (kalam still empty; length heuristic limit confirmed), freeze-bar genre coverage (next actionable empty genres: memoir, science).

## EXP-20260815-06 — Blind Opus re-audit of Miskawayh + Hariri shipping pairs

HYPOTHESIS: The Sonnet `aligned` that selected 24 Miskawayh and 37 Hariri pairs will not all survive a different model that never sees that verdict. Survivors join the standing 81 for the matched-prompt bakeoff; partials and failures stay out.
SETUP: `python -m versed_translator.benchmark.reaudit_shipping`, model `claude-opus-5` (selecting adjudicator was `claude-sonnet-5`). Blind: prompt carries no first verdict. Cache `reaudit_verdicts.json` per source dir; output `reaudit.jsonl`. One Miskawayh empty reply (`ah365-a016_021`, `stop_reason=end_turn`) retried at `max_tokens=16000` → `partial`. Two Hariri JSON dumps (`m02-a000_001`, `m48-a000_003`) retried at 16k and with a JSON-only nudge; both still continued Chenery saj'. Opus 5 rejects assistant-message prefill (`conversation must end with a user message`).
COST: 61 + 3 retry + 2 failed-prefill + 2 JSON-nudge Opus 5 calls. Replayable from the caches.
RESULTS:

| source | n | aligned | partial | unparseable | misaligned |
| --- | ---: | ---: | ---: | ---: | ---: |
| miskawayh_eclipse | 24 | 7 | 17 | 0 | 0 |
| hariri_assemblies | 37 | 32 | 3 | 2 | 0 |
| **total** | **61** | **39** | **20** | **2** | **0** |

Bands among Opus `aligned`: Miskawayh 4 short / 3 long; Hariri 14 short / 18 long. Unparseable ids stay out: `hariri_assemblies:m02-a000_001`, `hariri_assemblies:m48-a000_003`.
Bakeoff set: standing 81 + 39 survivors = **120**. File `~/versed-translator-data/benchmark-data/v0.1-draft/matched_prompt_eval_120.jsonl` (manifest beside it). Ibn Rushd's 2 selected pairs are not in this eval.
CONCLUSION: **Hariri mostly holds; Miskawayh mostly does not.** Sonnet's 24 Miskawayh `aligned` collapsed to 7 under Opus — the running-head lag the extractor warned about, now as a second-model finding, not only as a 70% first-pass partial rate. Hariri's maqama anchor survived (86% of parseable pairs aligned). The two saj' dumps are a model-behaviour failure, not a silent default to aligned. **Do not ship Sonnet-only Miskawayh. Do not retry those two Hariri ids. Proceed to matched-prompt on the 120.**
CAVEATS: not a human audit (Bilal waived shipping-page review; this pass is the substitute); unparseable ≠ misaligned and is not counted as aligned; CONTEXT gained a JSON-only sentence after the first 58 successes (cached, not re-judged); Miskawayh `ah365` used a 16k budget on retry.
DECISION FED: D2a (bakeoff set is 120, not 81+61), C1 (adab/maqama filled by 32 trusted Hariri; extra Miskawayh history is only +7).

## EXP-20260815-07 — Matched-prompt TranslateGemma 12B vs 27B on the 120

HYPOTHESIS: On the same prompt, same 663 blocks, same H100 / vLLM 0.11.0 / bfloat16 / temperature 0.1 / max_new_tokens 1536, 12B still holds ~99% of 27B chrF at materially less GPU time. The hadith-only 99.24% / 2.14× figure was prompt-confounded vs Claude and genre-narrow; this run isolates model size.
SETUP: Items `matched_prompt_eval_120.jsonl` (81 standing + 39 Opus-aligned). Blocks via current 60-word segmenter → **663** (mean 5.5/item, 7 blocks <9 words). `run_blocks` probes `structured_blocks_v1` then falls back. Prompt of record is `_run_summary.prompt_template_id`, expected `modal_minimal_v1` (literal in `matched_prompt_eval_120_protocol.md`). Protocol written before GPU jobs. 27B first attempt (`tg27b-modal-matched120`) is **not** this comparison: probe returned four parseable translations after `TemplateError`, so it ran structured and finished 646 ok / 17 parse errors. Probe gate fixed (`structured_probe_held`); 27B rerun to `tg27b-modal-matched120-fallback`.
COST: 12B 189.92 s GPU, est. $0.2084; 27B fallback 283.88 s, est. $0.3115 (H100 list $3.95/hr, NEEDS-VERIFICATION). First 27B structured leg 442.7 s / $0.49 extra, not in the comparison.
RESULTS: Both comparison legs recorded `prompt_template_id: modal_minimal_v1`, `structured: false`. Ingested `20260815T185422Z-modal-translategemma_12b` and `20260815T193612Z-modal-translategemma_27b`; reassembled against the 120-item file.

| | 12B | 27B fallback |
| --- | ---: | ---: |
| blocks ok / err | 663 / 0 | 661 / 2 |
| items ok / incomplete | 120 / 0 | 118 / 2 |
| chrF (all scored pairs) | 43.94 (n=120) | 43.57 (n=118) |
| chrF on 118 overlap | **44.11** | **43.57** |
| 12B as % of 27B (overlap) | **101.23%** | — |
| GPU wall | 189.9 s | 283.9 s (1.49×) |
| untranslated-Arabic items | 5 / 120 (4.2%) | 8 / 118 (6.8%) |
| id loss | 0 | 0 |

27B's 2 errors are `max_new_tokens_truncated` on Blunt verse blocks `labid-v052_083#b0001` and `harith-v018_048#b0002` — those two *items* incomplete on reassemble. 12B finished both.

Overlap chrF by source (n=118): Baladhuri 48.17/47.49, Hariri 43.35/43.21, Ibn Khallikan 43.65/42.92, Blunt 35.09/34.81 (n=12), Miskawayh 47.69/47.16, Ockley 43.84/42.51. 12B ≥ 27B in every source. Long band 44.70/44.11; short 43.09/42.65.

⚠️ Do not compare to the first 27B file. That run's label is `structured_blocks_v1`.
CONCLUSION: **12B remains the serving model.** On a matched weak prompt across history, biography, maqama, poetry, and philosophy, it is slightly *ahead* of 27B on chrF, 1.49× cheaper in GPU time, and did not truncate. 27B is not buying quality here. Next is one real book at 12B / blocks / `modal_minimal_v1`. chrF is still against abridging PD refs; it is a ranking signal, not a quality ceiling.
CAVEATS: `modal_minimal_v1` is weaker than harness `v1` (no six fidelity rules) — this unconfounds 12B vs 27B, not TG vs Claude; 2 Blunt items excluded from the fair chrF; untranslated-Arabic detector flags any Arabic codepoint (quotations count); 7 sub-9-word blocks on this slice; price constant unverified; first 27B structured yield (646/663) is a real "JSON almost held" finding but not this bakeoff.
DECISION FED: C2/C3 (12B confirmed on a diverse PD set), D2a (Modal gate: pick 12B and translate a book), D2e (blocks + honest prompt label).

## EXP-20260816-01 — Official TranslateGemma template 12B vs 27B on the same 120

HYPOTHESIS: EXP-20260815-07's 12B-ahead result was off-template. Google trains and evaluates Figure 3 (`ar`→`en`, text = Arabic only). On that API, 27B should at least not lose.
SETUP: Same 663 blocks. `prompt_mode=official` → checkpoint `apply_chat_template` with `source_lang_code=ar`, `target_lang_code=en`, `text`=Arabic only. No JSON probe, no `modal_minimal_v1`. Temperature 0.0, max_new_tokens 512, stop `<end_of_turn>`. Same H100 / vLLM 0.11.0 / bfloat16. Protocol written first: `official_template_eval_120_protocol.md`. Both legs recorded `prompt_template_id: translategemma_official_v1` and `prompt_modes: {official_chat_template: 663}` with empty `chat_template_errors`.
COST: 12B 173.4 s, est. $0.1903; 27B 323.8 s, est. $0.3553 (1.87×). H100 list $3.95/hr, NEEDS-VERIFICATION.
RESULTS: Ingested `20260816T044139Z-modal-translategemma_12b` and `20260816T044600Z-modal-translategemma_27b`. Each side truncated one different block (12B `blunt_odes:zuhayr-v016_044#b0002`; 27B `hariri_assemblies:m46-a048_059#b0003`), so fair chrF is the **118-item overlap**.

| | 12B official | 27B official |
| --- | ---: | ---: |
| blocks ok / err | 662 / 1 | 662 / 1 |
| items ok / incomplete | 119 / 1 | 119 / 1 |
| chrF on 118 overlap | 42.83 | **43.16** |
| 12B as % of 27B (overlap) | **99.25%** | — |
| GPU wall | 173.4 s | 323.8 s (1.87×) |
| untranslated-Arabic items (overlap) | 5 / 118 | **0 / 118** |
| id loss | 0 | 0 |

Overlap by source (12B / 27B): Baladhuri 47.31/46.79, Hariri 41.09/**42.62**, Ibn Khallikan 43.17/43.04, Blunt 34.68/**35.23**, Miskawayh 46.96/**47.23**, Ockley 41.60/41.56. 27B's lift is mostly Hariri.

On the 116 items all four legs finished: homemade 12B 44.24 / 27B 43.73 (12B 101.17% of 27B); official 12B 43.00 / 27B 43.32 (12B 99.27% of 27B). Official is **lower** chrF vs the PD refs than homemade (12B −1.24, 27B −0.41) — expected: Figure 3 is a modern MSA translator prompt, not "sound like Hitti/Chenery".

CONCLUSION: **The homemade-prompt inversion was real and is gone.** On Google's API, 27B is slightly ahead (99.25% the other way) and has zero leftover Arabic. Automatic scores still look like a tie. The serving call is the human read in EXP-20260816-02, not this table. Serve with `translategemma_official_v1`, not `modal_minimal_v1`. Do not overwrite EXP-20260815-07.
CAVEATS: chrF vs abridging 19th-c PD English; official prompt adds "cultural sensitivities" (honorifics showed up in samples); one truncation each, different items; 512 cap (not 1536); price constant unverified; no Classical Arabic language code exists — `ar` is MSA.
DECISION FED: C2 (call the model through the checkpoint template). Serving size is EXP-20260816-02.

## EXP-20260816-02 — Human read of the official 14-passage sample (Arabic as source of truth)

HYPOTHESIS: chrF vs abridging PD English understates 27B if the real gain is event structure, not lexical overlap.
SETUP: Bilal read `official_vs_homemade_compare.html` (14 of 120). Arabic is the source of truth; PD English is an expert historical comparator, not literal gold. Official-form 12B vs 27B are the systems under test. Full note: `~/versed-translator-data/benchmark-alignment/official_14_human_read.md`.
RESULTS: Prefer **27B on ~9–10/14**; poetry/technical often a tie because both fail; 12B only where 27B returned nothing. Surface F1 on the 14 is a hair (token-overlap .456/.465, chr-trigram .580/.588) — do not optimize that. Arabic leakage 6/14 vs 0/14.

**Scale repairs composition before historical semantics.** 27B is meaningfully better at syntax, discourse, participant tracking, long-prose coherence, and keeping Arabic out of English. It is not dramatically better at rare/polysemous CA words, administrative terms, archaic idiom, cultural allusion, or compressed verse.

Clean demo — Nihāwand `فدخل عمر المسجد فبصر النعمان…`: 12B reverses who saw whom; 27B keeps ʿUmar as subject. Same passage: 27B gets `زوال الشمس` (zenith not sunset), `بغلته` (mule), `السفطين` (chests not swords) and still misses `فرمونا` (stones for shots).

Scaling-resistant cliff — both write `نجوم المصادرات` as **stars**. Same cluster: `عشاء`→dinner, `المساحة`→generic control, `مناظرة`→debate, al-Barīdī→postal service, Luʾluʾ→Pearl, `سحيل ومبرم`→two people. 27B's fluency can make these *more* dangerous (invented Azraq; date 191→291 while the calendar frame is right).

12B's signature: participant collapse (`ليلة الجمعة` → a woman named Layla who is then buried). 27B's signature on verse: an English-shaped object that lost the metaphor (war as grind / gestate / wean).

Error clusters for later work (not a fine-tune target): **A** argument/referent structure (27B helps), **B** diachronic lexical sense (both fail), **C** entity typing (both; 27B can hide it), **D** technical register, **E** literary/allusive, **F** metalinguistic/philological, **G** fluent gap-filling, **H** leakage/truncation (27B wins H).
CONCLUSION: **Ship the book on 27B official.** Do not fine-tune on 12-vs-27 quality. Residual errors look like lexicon retrieval, entity-preserve, genre-conditioned prompting, and an uncertainty/gloss pass — especially verse as interlinear gloss then English. Proposed eval axes if we annotate the 14: participant/role, lexical-sense, entity integrity, technical-register, figurative/allusive, uncertainty calibration; completeness/leakage as mechanical gates.
CAVEATS: n=14 curated (problems + one per source), not a blind sample of 120; one reader; PD refs still abridge.
DECISION FED: D2a (book on 27B / `translategemma_official_v1`), C2 (do not treat chrF-vs-PD as the quality gate), C4/C5 later (lexicon/entity, not size).

## EXP-20260816-03 — Qwen-MT + Gemini Flash / Flash-Lite on the frozen 120

HYPOTHESIS: Dedicated cheap MT (Qwen-MT) and Gemini Flash-tier chat-as-MT have never been scored on this set. On the same 663 blocks they will at least produce usable English and measured token usage, replacing the unmeasured Gemini-batch envelope.
SETUP: Same `matched_prompt_eval_120_blocks60.jsonl` (663). Protocol written first: `api_bakeoff_120_protocol.md`. One block per call (not JSON structured). Qwen: `qwen-mt-turbo`, DashScope **intl**, template `qwen_mt_v1` (Arabic-only user turn), `translation_options: {source_lang: Arabic, target_lang: English}`, no `max_tokens`. Gemini: OpenAI-compat `https://generativelanguage.googleapis.com/v1beta/openai`, template `plain_mt_v1`, `--omit-max-tokens` (thinking-budget trap). Models `gemini-flash-lite-latest` then `gemini-flash-latest`. Not harness `v1` — that would re-confound prompt with model.
COST: API list prices NEEDS-VERIFICATION. **Measured usage** (provider `usage`):

| leg | wall_s | in tok | out tok | block err | est. if using unverified list notes |
| --- | ---: | ---: | ---: | ---: | --- |
| Qwen-MT turbo | 791.5 | 84,363 | 71,205 | 0 | tokens only; DashScope invoice not pulled |
| Gemini Flash-Lite | 712.6 | 71,906 | 68,392 | 2 | tokens only |
| Gemini Flash | 2853.2 | 71,805 | 70,343 | 3 | ~4× slower than Lite (thinking) |

Naïve $/M Arabic words cannot be billed from these until the current price table is confirmed. Do **not** reuse a $650 / 2B-word Gemini envelope — that was never measured here.
RESULTS: Ingested/reassembled under `~/versed-translator-data/runs/`. Scores: `benchmark-alignment/api_bakeoff_120_scores.json`. Compare HTML (same 14 ids as EXP-20260816-02): `benchmark-alignment/api_vs_official_compare.html`.

Fair chrF on the **115-item overlap** (every system finished the item):

| system | chrF overlap | leftover AR overlap | notes |
| --- | ---: | ---: | --- |
| Gemini Flash | **47.06** | 0 | 3 incomplete items overall |
| Gemini Flash-Lite | 45.80 | 0 | 2 empty-content blocks (`labid-v035_051#b0003`, `m01-a001_011#b0001`) |
| Qwen-MT turbo | 44.78 | 0 | **663/663 ok**, 120/120 items |
| TG 27B official | 43.20 | 0 | EXP-20260816-01 |
| TG 12B official | 42.88 | 5 | EXP-20260816-01 |

Qwen all-120 chrF **44.63**, leftover Arabic **0/120**. Gemini Flash all-scored chrF **46.94** (n=117). Overlap-by-source: APIs ahead in every source; largest gaps Hariri and Blunt.

Known-cliff spot-check (`miskawayh_eclipse:ah325-a000_005`): Qwen, Flash-Lite, and Flash all keep **Barīd** and **Luʾluʾ** as names; official 27B had typed them as postal service / Pearl. This is **not** a human verdict on `نجوم المصادرات` (stars) — that still needs the Arabic-as-truth read.
CONCLUSION: **The API legs are now measured, not hypothetical.** Automatic chrF-vs-PD ranks Gemini Flash > Flash-Lite > Qwen-MT > TG27B official > TG12B official. That ranking is still against abridging 19th-c English; it does **not** by itself replace EXP-20260816-02's serving decision. It does kill the claim that we have no quality evidence for Qwen/Gemini, and it makes a human 14-passage read of `api_vs_official_compare.html` the next quality gate for “first corpus via API vs owned 27B.” C8 still requires an open, fine-tunable model for the model we publish — that remains TranslateGemma. No model was trained. ATHAR still cannot be release data.
CAVEATS: chrF vs PD; Gemini empty-content on two verse/maqama blocks (same ids on Lite and Flash); one Flash `RemoteDisconnected`; Flash wall includes thinking tokens; prices unverified; no human read of the API 14 in this entry.
DECISION FED: D2a (API corpus-route is now an evidenced option, not a spreadsheet); D2c (Gemini provisioned *and* scored); C8 (open model ≠ cheapest API); publication path (PD 120 + our outputs, never ATHAR).
NOTE (same day, do not overwrite numbers above): the human read is **EXP-20260816-04**. Do not treat “Qwen 120/120” in this entry as the first-corpus quality decision.

## EXP-20260816-04 — Arabic-first human read of the API 14 (TG27 vs Qwen vs Flash-Lite vs Flash)

HYPOTHESIS: chrF-vs-PD (EXP-20260816-03) understates the human gap; Qwen’s 120/120 and 0 leftover Arabic may be completeness rather than Classical-Arabic fidelity.
SETUP: Same 14 ids as EXP-20260816-02, page `api_vs_official_compare.html`. Arabic = source of truth. Two independent reads (0–5 and letter grades) then a convergence pass. Full note: `~/versed-translator-data/benchmark-alignment/api_14_human_read.md`.
COST: human time only.
RESULTS: Flash won every passage card. Converged grades: **Flash A−, Flash-Lite B/B+, Qwen C+, TG27 C− with F-class tails.** Bilal means 4.54 / 3.93 / 2.69 / 2.26 (not a validated metric).

Checkable publication-blocking exhibits on TG27: (1) Miskawayh ah325 entity dissolution (Barīdī→postal service, Luʾluʾ→Pearl, regiments→dam/stone, بطالبي dropped) that rewrites the plot; (2) Ibn Khallikan 0362 **191 AH → 291 AH**; (3) Labid multi-sentence confabulation with no Arabic anchor; (4) Hariri m46 no output. Qwen keeps some names but substitutes Kharijites / Maysan / “wrote about him.” Flash alone holds `نجوم المصادرات` through the anaphor (installments, not stars). Flash-Lite holds the ah325 names and many scenes; loses the `نجوم` anaphor.

**Correction:** `كتبت عنه` is Ibn Khallikan `v2-bio-0442`, not Hariri m20. Hariri m20 is the Mayyāfāriqīn maqāma (Qwen → Maysan).

CONCLUSION: **Reject raw TG27 and Qwen as quality leaders for the first corpus.** Flash is the human-quality leader on this diagnostic; Flash-Lite is the serious cheap challenger; Qwen is operational fallback. TG27 remains the **open model to own and fine-tune**, not “what we would publish as translations.” Do not treat 0 leftover Arabic as quality. Next quality test is **blind untranslated OpenITI** (no PD ref, no chrF, grade + catastrophic flags) because these 14 are famous and possibly in Gemini’s training data. The 27B book run is factory/FT baseline, not the corpus-producer decision.
CAVEATS: n=14 curated famous works; two readers, poetry ranking is judgment; entity/date/term errors are hard-checkable; contamination untested.
DECISION FED: D2a (first corpus: Flash, pending blind-20; owned model still TG27), C2 (chrF-vs-PD cannot be the ceiling), C8 (teacher for a future student may be Gemini, not ATHAR), C5 (poetry routing; entity/date flags).
NOTE (same day): **EXP-20260816-05** revises C8 — do not distill Gemini API output into TranslateGemma until counsel clears the API competitive-use clause. Factory v1 is verifier-first, not router-first.

## EXP-20260816-05 — Factory v1 decision + Fable r1 export

HYPOTHESIS: At corpus list prices the Lite-vs-Flash gap is ~$5k / 2B words; a learned router is not the product. Verse must be pre-routed; everything else is Lite + glossary + invariants + extractor-judge + 2% audit.
SETUP: Decision recorded in `~/versed-translator-data/FACTORY_V1.md`. Fable export: 50 stratified passages from the frozen 120 **excluding** SAMPLE_14, × TG27 / Flash-Lite / Flash / Qwen = 200 rows, seed 20260816, two 100-row CSVs. Qwen is in the *label* set as a failure source, not in production. PD English omitted from the CSV.
COST: none (export only). Gemini/Qwen list $ at 2B remain unbilled inferences (~$1k all-Lite vs ~$6k all-Flash).
RESULTS: files under `~/versed-translator-data/benchmark-alignment/fable_r1/`. No new model scores. Glossary A/B and invariants checker not run in this entry.
CONCLUSION: **Ship the cascade, not a classifier.** Labels from Fable serve checker tests, glossary rows, and a licensing-clean TG curriculum (human flags + TG-shadow), not Gemini matn. Google Translate can join the same 50 ids in a later round as known-bad input to the checker.
CAVEATS: 50 are still famous PD-paired works (contamination); Blind-50 untranslated OpenITI remains the generalization test. ToS reading is not legal advice.
DECISION FED: D2a (factory = Lite+glossary with Flash escalate), C5 (invariants + extractor-judge, not MetricX), C8 (no Gemini→TG distill until cleared), D5 (publication gate = zero blocking flags + 2% audit).
NOTE (same day): **EXP-20260816-06** reclassifies the r1a sitting as `silver_error_harvest` and records the first implementable cascade simulation. Do not read this entry as a production routing decision or as glossary gold.

## EXP-20260816-06 — r1a reclassified silver; cascade router simulated

HYPOTHESIS: r1a can train draft checker rules and a glossary *candidate* table, and we can simulate an implementable Lite→check→Flash cascade on those silver labels — without treating Fable 24/25 vs 12/25 as a production routing result, and without a learned source-router.
SETUP: Preserve r1a outputs, Fable prompt/rubric, and digest. Normalize 93 pipe-joined mined rows → 111 `glossary_candidates` (`status=candidate`, `train_eligible=false`). Retrieve only entries whose Arabic occurs in that passage and book. Cascade: verse/sajʿ → Flash; else Lite; CORE_CHECKS + glossary contradiction; on fail keep Lite *and* fetch Flash; ship Flash only if Flash's own checks are clean; if both dirty, keep Lite and queue human. Code: `versed_translator.factory`. Simulation file: `~/versed-translator-data/benchmark-alignment/fable_r1/policy_sim_r1a.json`. Audit sample: `audit_r1a_24.csv`. Unseen same-book holdout (16 Baladhuri + 8 Ibn Khallikan, disjoint from the 50 Fable ids and SAMPLE_14): `glossary_holdout_24.jsonl`. No API 2×2 in this entry.
COST: none (offline).
RESULTS: Fable descriptive (single-model-rater, not a conclusion): Flash 24/25, Lite 12/25, Qwen 0/25, TG 0/25. Oracle Lite-else-Flash 25/25 — not implementable. Implementable checker-auto (keep both, human catches queued): **21/25**, 4 escaped, 15 Lite escalations, 6 human, 9 auto-Flash. Naive overwrite-on-fail: 20/25 (worse). Lite checker vs Fable: recall 0.69 (9/13), 6 false escalations, 4 escaped TERM/ENTITY sense errors. The s32 Lite-Y / Flash-N disagreement: Lite false-tripped NEGATION, Flash also failed checks, cascade kept Lite and queued human. Verse gate is a no-op on r1a (chronicle/bio). CORE_CHECKS-only previously caught 15/64 blocking across all four systems; glossary retrieve is what moves Lite recall. A logistic on check features still loses to always-N and leaks system voice — do not train a publishable-Y/N classifier on r1a.
CONCLUSION: **r1a is `silver_error_harvest`.** No production routing policy. The router we ship next is the cascade, not a neural net. The classifier *starts* as deterministic checks + per-passage glossary retrieve. Gemini outputs and Fable labels remain analysis-only (`train_eligible=false`); an open-source scientific checker is still not a license to copy those texts into TranslateGemma. Next: human-audit the 24, verify glossary candidates against independent sources, then the 2×2 on the holdout; r1b for verse/Miskawayh/ADDITION.
CAVEATS: labels are Fable silver; escaped-4 are unconfirmed; glossary entries are candidates (`الحلقة` must not mean mail-armor everywhere); r1a cannot test a learned source-router or a production cascade; holdout 2×2 not yet run.
NOTE (same day): **EXP-20260816-07** is the blind Fable regrade of the hard-24 close calls. Still silver. Do not read 13/15 Lite fails as the r1a base rate — that sample is Lite-heavy by design.

## EXP-20260816-07 — Blind Fable regrade of r1a hard-24

HYPOTHESIS: A second Fable sitting, labels hidden, on the 24 close-call outputs will show which first-pass Y/N calls are stable and whether Flash-Lite's damage is a lexical-substitution pattern the glossary checker can target.
SETUP: Same 24 rows as `hard24_for_fable.csv`. First-pass grades stripped. Rubric unchanged (Arabic as truth, closed flags, N iff blocking). Artifact: `~/versed-translator-data/benchmark-alignment/fable_r1/hard24_fable_regrade.csv`. Compare: `hard24_compare.csv`.
COST: Fable sitting only.
RESULTS: Arabic/translation byte-identical 24/24. **5 Y / 19 N.** Publishable agreement with pass 1: **20/24 (0.83).** All four overturns were Y→N (0011 Flash مأثرة "feud"; 0006 Lite الحصر "guarding the passes"; 0026 Lite broken dispatch; 0058 Lite "Umm Ibrāhīm, the son of the Messenger"). No Y/N flips toward pass; the three "lenient" notes (0030 hadra, 0055 ajlā', 0074 nisba) were already Y. Flag-set shifted on six further rows that kept Y/N (e.g. 0029 TERM→ROLE isnad "about" vs "from"; 0073 OMISSION→ROLE taṣliya). Confidence 13 high / 11 med / 0 low.

This 24 is adversarially Lite-heavy (15/24). Pass-2 Lite **2/15 Y**; Flash **3/5 Y**. Do not quote 13/15 as the r1a Lite rate (first sitting on all 25 Lite was 12/25 Y). Lite's recurring signature here is unhedged substitution on a rare lemma: سن→age, المورَّد→watering place, اصطفوا→aligned themselves, روح→the spirit, المصرين→Egypt and Syria, الحصر→guarding the passes, نفض الأيدي→shaking hands. Flash's two fails are the softest in the set (stamped-hands 0031, مأثرة 0011), both med. s32 Lite-Y / Flash-N **held** across both sittings.

The med rows Fable flagged for a later dad look: 0031, 0042, 0006.
CONCLUSION: Second silver sitting, not gold. The cascade still must keep both outputs (s32 non-nested, stable). Checker next step is those substitution lemmas as glossary retrieve signals — not a learned "rare word + confident English" classifier on 15 rows. ROLE/isnad/apposition (0029, 0058, 0073) will not be caught by exact glossary match.
CAVEATS: Same model family as pass 1; 0.83 agreement is self-consistency, not human agreement. Sample bias toward Lite close calls. Semicolon vs pipe in flags this sitting.
DECISION FED: D2a (keep-both escalate still required), C5 (glossary contradiction for Lite substitutions; ROLE still semantic).
NOTE (same day): **EXP-20260816-08** consolidates the two sittings into silver consensus plus a deferred dad-review queue. Not human gold. No current human gate.

## EXP-20260816-08 — hard-24 two-sitting Fable consensus; deferred review queue

HYPOTHESIS: The completed blind second sitting can be merged with the first sitting into model-consensus labels for checker/router development, without calling Fable again and without a human gate.
SETUP: Inspected `hard24_for_fable.csv`, original `fable_r1a_graded.csv`, `hard24_fable_regrade.csv`, and the prior dad file. Second sitting present (24 rows, grading filled). Did not call Fable. Classifier: `versed_translator.factory.consensus`. Arabic/translation copied from the sent file after verifying identity with both sittings.
COST: none.
RESULTS: Y/N agreement **20/24**; four unresolved Y→N flips (0006, 0011, 0026, 0058). Label status: **2 silver_consensus_high**, **15 silver_consensus_med**, **7 disputed**. Priority: **P1=7, P2=15, P3=2**. Disputed = the four flips plus three both-N rows whose blocking class has no overlap (0029 TERM vs ROLE, 0032 ADDITION vs TERM, 0073 OMISSION vs ROLE). Consensus publishable left empty on disputed rows. No row labelled human_gold. Round-trip Arabic/translation strings unchanged.
CONCLUSION: **hard-24 = two-sitting Fable consensus plus deferred human-review queue; not human gold; no current human gate.** Stable silver-consensus rows may support checker/router development. Disputed rows are challenge cases, not training or benchmark truth. Dad CSV is parked and sorted P1→P3; `dad_*` empty. Subsequent work uses the 17 consensus rows and continues (r1b, glossary 2×2) without waiting.
CAVEATS: Same model family both sittings; 20/24 is self-consistency. Sample is Lite-heavy close calls.
DECISION FED: D2a / C5 (develop on silver consensus; park disputed).
NOTE (same day, evening): **EXP-20260816-09** closes r1a. No third sitting. Sequence is r1b once → glossary 2×2 → policy sim on 200 → one book.

## EXP-20260816-09 — r1a closed; factory is the product

HYPOTHESIS: Further grading-the-grader on r1a cannot exit. The four keepers from the day are enough; the factory run is the next source of router labels.
SETUP: r1a first sitting + one blind hard-24 regrade. Consensus file exists and is frozen. r1b (`fable_r1b.csv`, 100 rows, ungraded) is the only remaining Fable sitting in round 1.
COST: none this entry.
RESULTS kept: (1) `glossary_candidates.csv` n=113; (2) Fable self-agreement 20/24, all flips Y→N — first-pass leniency is known, no third sitting; (3) probe collinearity — English-side models learn system voice because TG/Qwen are 0/25; learned router is Arabic-only and not yet; (4) cascade keep-both 21/25, checker recall 0.69, four misses are sense errors (judge layer). Apparatus skipped going forward: consensus-tier refinement, evidence-class tables as a workstream, r2b, any further r1a pass.
CONCLUSION: **r1a is closed.** Checker = (Arabic, English) → flags, trained on all system failures. Router = Arabic-only → P(publishable|Lite/Flash), labels = factory gate outcomes, harvested in production, trigger ≥500 gate-labeled passages or Blind-50. Until then the router is the verse/sajʿ rule + Lite→check→keep both. Ship test: beats two if-statements on Blind-50 escaped-blockers per Flash-dollar. Next: Fable grades r1b once; glossary 2×2 with `verified_by=fable_evidence` (no human-verify deadlock); policy sim on 200; one book with TG shadow.
CAVEATS: r1b not yet graded; 2×2 not run; book not started.
DECISION FED: D2a (factory first), C5 (checker after translation; learned router parked), C8 (no Gemini→TG).

## EXP-20260817-01 — r1b sitting merged; round 1 closed

HYPOTHESIS: One Fable sitting on the hard half (verse / sajʿ / Miskawayh / Ḥayy) completes the 200-row silver label set, lets the verse gate fire in the cascade sim, and tests whether chrF ranking survives meaning-level flags.
SETUP: `fable_r1b.csv` (100 rows) graded in `fable_r1b_graded.csv` against `PROMPT_r1b.md`. Verified: 100 rows, source columns untouched, publishable ⇔ zero blocking flags. Merged with r1a → `fable_r1_graded.csv` (200). `check_output` now treats empty/`nan` English as MISSING. Policy sim: `policy_sim_r1.json` (50 passages), `policy_sim_r1b.json` (25). Digest: `DIGEST_r1b.md`. Did not call Fable. Did not open r1a. Did not merge noisy TERM spans into the 113-entry glossary (raw dump: `r1b_term_harvest.csv`).
COST: one Fable sitting (grader); merge/sim offline.
RESULTS: r1b Flash **24/25**, Lite **11/25**, TG27B **2/25**, Qwen **0/25**. 37/100 publishable. Flags on 63 N: TERM 60, ENTITY 26, ROLE 24, NUMBER 5, OMISSION 3, ADDITION 3, MISSING 2. Combined round 1: Flash 48/50, Lite 23/50, TG 2/50, Qwen 0/50. Both Flash and Lite empty on Labid `blunt_odes:labid-v035_051` (`fable_r1-0150/0151`) — a generation miss, not a translation; Flash’s true r1b score may be 25/25 if that item is rerun. chrF had ranked Flash 47.06 > Lite 45.80 > Qwen 44.78 > TG 43.20; meaning-level Flash 24 vs Qwen 0. Keep-both on 50: **46/50** (verse gate 14/50, 14 human, 10 auto-Flash). Escaped 4 = three r1a Lite sense errors the checker still reads clean + the empty Labid. Overwrite 45/50. All-Flash 48/50. Oracle 49/50 (only the empty pair). Lite checker recall 0.778 on 50. Flash checker recall 1.0 / precision 0.08 — do not overwrite. TG’s two Ys are the simplest Ḥayy narrative sections.
CONCLUSION: **Round 1 is closed.** The flag layer cannot be replaced by chrF; Qwen’s seamlessness is the danger. Flash-Lite failures are local (extractor-judge / glossary); TG/Qwen failures are global. The informative classifier boundary is Lite’s mixed 23Y/27N, not the 200-row pool. Do not train on these labels. Next experiment is the glossary 2×2, then one book with Lite-tier gate logging. Optional: rerun Labid `v035_051` for Flash only — not another sitting.
CAVEATS: single-model-rater silver; 18 med-confidence rows (13 Lite) are a deferred dad packet; three closest Lite Ys (0182, 0134, 0162) could flip; shared cruxes were ruled cosmetic under 3–4/4; 2×2 not run; book not started.
DECISION FED: D2a (keep-both cascade; Qwen out), C5 (flags not chrF; checker after translation; learned router parked on Lite-tier harvest), C2 (chrF-vs-PD cannot be the ceiling).

