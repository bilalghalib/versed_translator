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
