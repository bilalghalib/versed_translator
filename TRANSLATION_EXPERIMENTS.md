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
