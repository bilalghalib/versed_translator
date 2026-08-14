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

## EXP-20260814-02 — MetricX-24 as a shippable second QE opinion (C4)

HYPOTHESIS: MetricX-QE is (a) permissively licensed enough to ship, and (b) covers COMETKiwi's fidelity blind spots.
SETUP: `google/metricx-24-hybrid-large-v2p6` (apache-2.0, ungated) + `google/mt5-large` tokenizer, reference-free mode, CPU. Input `"source: {src} candidate: {hyp}"`, `max_length=1536`, EOS stripped after truncation (MetricX trained in T5X without EOS). Score is error on [0,25], lower better → **negated inside the scorer closure** so the engine's higher-is-better contract holds. Threshold 0.5 (= 2% of scale, matching COMETKiwi's 0.02/[0,1]; independently ≈ half an MQM minor error).
COST: negligible (CPU, local). ~6.2 s/segment.
RESULTS (**SMOKE ONLY — 20 items / 162 pairs / 324 segments**): `~/versed-translator-data/qe/tg27b-smoke20-metricx/`. Overall detection 33.3%. Score range [−20.17, −1.68] over 139 distinct values (not constant — plausibility check passes). Beats COMETKiwi on `omit_person` (0.65 vs 0.30), `leave_arabic_untranslated` (0.60 vs 0.35), `remove_clause` (0.53 vs 0.23), `hallucinate_prose` (0.55 vs 0.42). **Shares the same critical blind spots: `delete_negation` 0.0, `mistranslate_term` 0.0, `reverse_agent_patient` 0.0.** Full 1,144-pair run launched detached 2026-08-14 12:36 (~3.8h; sentinel `~/versed-translator-data/logs/done-metricx-full`).
⚠️ CONFOUND: **126/324 inputs (39%) hit the 1536-token cap.** Truncated inputs show median clean error 17.51 vs 8.88 for inputs that fit — truncation roughly doubles apparent error, and it eats the END of the input, i.e. the candidate being judged. Length-increasing injectors are truncated more than their clean counterparts, biasing deltas toward zero. The `duplicate_sentence` row (−1.49 mean delta, 5%) is an **artifact of the cap, not a property of MetricX**. Instrumented, not fixed: the scorer counts truncations and the runner stamps `truncated_inputs`/`truncated_fraction` into the summary. → D4c.
CONCLUSION (partial, pending the full run): (a) **confirmed** — apache-2.0 and ungated, the first reference-free QE model here that shipping code may require; (b) **refuted** — MetricX misses negation deletion, terminology substitution, and agent/patient reversal as completely as COMETKiwi does. Two independent neural QE systems failing on the same three highest-severity fidelity errors is much stronger evidence for the deterministic-check ensemble than one was.
CAVEATS: smoke-scale n; hadith-only slice; the 39% truncation confound above; MetricX has never seen isnad chains or honorifics, so the median 8.88 error on *clean* 27B output may be domain mismatch rather than a quality signal — undetermined without human labels.
DECISION FED: D4b (shippable mode has a viable neural signal), D4c (token-window handling), C5 (deterministic checks remain load-bearing, not a stopgap).
