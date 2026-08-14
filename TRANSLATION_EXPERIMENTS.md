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
