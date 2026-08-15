# STATUS

**The only operational handoff. Start here; don't read the roadmap first.**
Last updated: 2026-08-15

Four documents, four jobs. Nothing else is a source of truth:

| File | Job | Changes |
| --- | --- | --- |
| **STATUS.md** (this) | where we are, what's next | constantly |
| `VERSED_TRANSLATE_MASTER_PLAN.md` | the destination and why | **frozen** — vision only, never today's state |
| `TRANSLATION_EXPERIMENTS.md` | every measurement, with caveats | append-only |
| `VERSED_TRANSLATION_ARCHITECTURE.md` | where translation attaches to the factory | rarely |

`VERSED_TRANSLATION_ROADMAP.md` keeps the component END STATEs and their `Verify:` checks — the contracts that let an agent know when it's done. It is a reference, not a status board. **Numbers live in the ledger, not in the roadmap.** GitHub issues labelled `decision` are the canonical decision record; the dashboard is generated and authoritative for nothing.

---

## Current objective

**Get one substantial Classical Arabic book translated end to end through the Versed pipeline** — block-preserved, provenance-recorded, automatically checked, human spot-audited, readable on versed.page.

Not a 5,000-item benchmark. Not a fine-tune. Not a calibrated QE ensemble. Those come after, and the pilot de-risks the factory independently of model quality — which is the point.

## What we know (all measured; details in the ledger)

- **TranslateGemma 12B is the working choice.** 99.24% of 27B's chrF for 2.14× less GPU time, 2.1× lower latency, $0.20/139 items, and zero untranslated-Arabic rows (27B had 2, Claude 3). *Hadith-only, and TranslateGemma ran on a weaker prompt than Claude, so it is understated.*
- **Neural QE cannot be the safety gate.** COMETKiwi 30.4% and MetricX 30.7% — two independent systems agreeing within 0.3 points **and blind to the same three critical errors**: agent/patient reversal 0%, terminology ~1%, negation deletion ~10%. Not one model's quirk; a property of reference-free QE. The deterministic checks are the gate.
- **MetricX is the only shippable neural signal** (Apache-2.0). COMETKiwi is CC-BY-NC — research mode only, never required by shipping code.
- **Structured blocks work.** Truncation 0.3754 → 0.0073; ID loss is now a run-level metric and caught a live 2.5% omission on first use. Cost: −0.65 chrF. Blocks also make QE ~1.6–2.0× *more expensive* (sub-linear CPU scaling) — the argument for QE on Modal.
- **PD references abridge.** Hitti retains only 40% of Arabic narrator markers. Alignment quality and reference fidelity are different properties, tracked as different fields. Never train isnad handling on these.
- **Alignment from PD translations works.** 39 Baladhuri/Hitti history passages, human-audited **15/15 aligned**, no one-report shift.
- **The whole selected set survived an independent blind re-audit (2026-08-15).** All 81 passages re-verified: **73 aligned / 8 partial / 0 misaligned**; 24/24 sampled rejects genuinely bad, zero over-rejection. The 8 partials are edge jitter only (Ockley ±1 sentence, Blunt half-verse smear, 2 Baladhuri trailing reports) — fix or trim at freeze. EXP-20260815-01.
- **ATHAR's English side is verbatim in-copyright translations** — Rosenthal 1958 and Faris 1952 word-for-word, ~3/4 of pairs with no PD English source in existence; the HF CC labels are legally ineffective (rasaif owned nothing to license) and re-scraping rasaif changes nothing. ATHAR stays `eval_internal` forever; PD alignment is the only rights-clean public reference side. EXP-20260815-01.
- **Miskawayh year-anchor + mandatory adjudication works, at a 20% aligned yield.** 504 proposals, 120 year-spread judged, 24 selected (15/9 across the two bands). 70% came back `partial` — the running-head page lag, caught. Driver: `python -m versed_translator.benchmark.miskawayh_alignment`. Shipping page exists. History is over the 40% cap; do not mine this source further. EXP-20260815-02.
- **Sources are not the constraint.** Catalog sweep (complete Gutenberg + archive.org) found Miskawayh 383 paragraphs ≥250 words, Suyuti 211, Payne's *Nights* 133–151 per volume × 10, Ibn Rushd at the best text quality measured. Miskawayh and Sachau's Biruni print Arabic page numbers inline — free hard anchors. Next empty high-value genre is Hariri's *Assemblies* (adab/maqama).

## What is running

- Nothing. Miskawayh adjudication finished (sentinel `done-adjudicate` = 0). The block-level MetricX detection matrix also finished earlier (sentinel `done-metricx-blocks` = 0; outputs in `~/versed-translator-data/qe/tg12b-blocks-metricx/`); its read-out is still not in the ledger.

## Next 3 things

1. **Human-review the Miskawayh shipping page, then leave this source.** Driver is wired and ran: 504 proposals → 340 eligible → 120 year-spread adjudicated → **24 aligned selected** (15 in 100–250, 9 in 250–600, 22 years). Yield was **20% aligned / 70% partial / 10% misaligned** — the within-year running-head lag the extractor warned about, caught rather than shipped. Review only `~/versed-translator-data/benchmark-alignment/miskawayh_eclipse/review_shipping.html` (spot-check 10–15). **Do not run another Miskawayh round and skip Suyuti for now** — both are `التاريخ`, and history is already over the 40% cap. The take from this source is the 9 long-band passages. Next diversification work is **al-Hariri / Chenery–Steingass *Assemblies*** (adab/maqama, catalog-ranked #1, empty genre).
2. **Matched-prompt TG12B vs TG27B** on exactly the frozen set: same blocks, same prompt, same decoding, same hardware assumptions. Then **read ~50 outputs by hand, blind to model where possible**, oversampling long passages and the errors chrF and QE are measurably bad at — omission, negation, agent/patient reversal, terminology, quotations, narrator chains. Record **D2a**.
3. **Then stop benchmarking and run a real book.** One substantial work through the full path. Do not let "we should first improve QE" or "maybe one more genre" interpose unless step 2 revealed a genuinely blocking failure.

---

## 🛑 STOP CONDITION FOR BENCHMARK WORK

**v0.1 is done — freeze immediately and proceed to the matched-prompt comparison — when it has:**

- **300–500 trusted passages**
- **6–10 materially different genres**, and **no single genre >40%** (without this check, "genre-diverse" can still quietly mean "mostly hadith")
- **meaningful representation of both the 100–250 and 250–600 word bands**
- enough **rights/provenance metadata** for internal evaluation
- **contamination-clean references**: every gold pair freshly aligned by us from PD editions (mid-scan passages that mostly don't exist online in aligned form) — never copied from ATHAR/rasaif rows, which are plausibly in TranslateGemma's training soup and would flatter the base model

That is the whole bar. It exists to stop v0.1 expanding back into the 2,000-item project by accretion. The publication-grade set (2,000–5,000 items, 10+ genres × 4 bands × 5+ centuries, private holdout, SHA manifest, contamination CI) is **v1.0**, required before serious fine-tuning claims — not before useful experiments.

## Human decisions needed

**None open.** `gh issue list --label decision` is the live check; all six from 2026-08-14 are answered and closed.

The one standing ask, when the small benchmark exists: **label passages** "would a competent bilingual editor find a substantive error?"

⚠️ The invariant to protect is narrow: **no threshold fitting on the samples used to claim router performance.** Designate a disjoint calibration subset *when Versed-QE is actually calibrated*, keeping an untouched evaluation slice. v0.1's primary job is model and architecture selection — do **not** pre-split it into two frozen halves now.

## Known traps — do not re-derive

- A full row count, clean exit code and populated output file are **all compatible with total failure**. A 139-row run was 139 connection errors; the tell was `wall_s: 0.06`. Check the error field *and* a plausibility signal.
- **A metadata label is not evidence.** Both Modal legs recorded `prompt_template_id: "v1"` while sending something else; the bakeoff's headline comparison was confounded for a day and nothing failed.
- `nohup … & disown` does not survive session teardown, and **`setsid` does not exist on macOS**. Use `subprocess.Popen(..., start_new_session=True)` locally, `modal run --detach` for Modal, and write a `done-<job>` sentinel with the exit code.
- vLLM 0.11.0 allows `transformers` 5.x, which renamed `rope_scaling`. Pin `transformers<5`. Patching the model's `config.json` does **not** help — three attempts proved it, and a stale comment claiming otherwise was corrected.
- Sonnet 5's `max_tokens` caps thinking **plus** text; too small a budget returns empty translations.
- Local CPU inference for a 12B is ~2 tok/s. Inference happens on Modal.
- `/Volumes/hikma` (SMB) degrades mid-session to permission-denied at the share root. Read the corpus via `ssh nautilus` (`/mnt/hikma`).
- PDF rendering needs Homebrew's GTK stack: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib GI_TYPELIB_PATH=/opt/homebrew/lib/girepository-1.0 ~/mambaforge/bin/python`. Verify Arabic output **visually** — PyMuPDF `get_text()` returns visual order for RTL, so broken and correct look alike.
- **`review.html` is triage, not the benchmark** — all proposals, worst-first, rejects included. Reading it as the shipped set has caused a false "alignment is broken" alarm **twice** (Baladhuri, then 2026-08-15). Humans review `review_shipping.html` (selected-only, best-first); every source must generate both.
- **Model tier ∝ blast radius, not text difficulty.** Volume work (OCR cleanup, tagging, dedup) → cheap models in parallel; propagating decisions (rights calls, adjudication verdicts, benchmark verification) → top tier with thinking budget. Nothing below top tier writes a rights determination.

## On pause — resuming from Cursor or any other tool (2026-08-15)

Claude Code usage limits paused mid-sprint; Cursor continued and landed the Miskawayh driver. Whoever resumes — read this file top to bottom first, then:

**Done in this Cursor session (do not redo):**
- `miskawayh_alignment.py` extract→adjudicate→select→write CLI, tests, both review pages, incremental verdict cache, cache-replay so a second `--adjudicate` round skips paid-for items.
- First adjudication run finished: 120 of 340 eligible, **24 selected**, shipping page at `~/versed-translator-data/benchmark-alignment/miskawayh_eclipse/review_shipping.html`.
- `render_shipping_page` now lives in `alignment_review.py`; Baladhuri / Ibn Khallikan / Ockley / Blunt drivers also emit `review_shipping.html` on the next run (existing Baladhuri shipping page was a one-off HTML file).

**Safe anywhere, no credentials (`uv run`):**
- Spot-check the Miskawayh shipping page is well-formed (it is); regenerate dashboard (`make -f tools/dashboard.mk dashboard`).
- Start the **Hariri** extractor/driver — adab/maqama, catalog-ranked #1, empty genre, notes-free `The Assembly of Al Hariri All 50_djvu.txt`. Mirror `sequence_alignment.py` or `miskawayh_alignment.py` (maqama units are discrete; likely closer to Blunt/Ibn Khallikan than to year-blocks). Tests, review pages.
- If a future candidate lacks structural anchors, trial embedding candidates (SONAR/LaBSE + vecalign-style DP) before another length heuristic — length-only ran 3–5× worse than anchors (Ockley 7/53). Not a reason to touch working extractors.

**Needs credentials (on this Mac, never in the repo):**
- Bilal's eyes on 10–15 Miskawayh shipping pairs. A proposal is not a passage; an `aligned` verdict is not a human audit.
- Further LLM adjudication (`ANTHROPIC_API_KEY`) — **not for more Miskawayh**. History is over cap.
- Modal runs (matched-prompt TG12B-vs-27B) — `~/.modal.toml`. **Do not start until the set is frozen.**
- `gh` (decisions live as issues), `ssh nautilus` (OpenITI corpus reads).

**While on pause, do NOT:** freeze the benchmark below the stop-condition bar; write a rights determination without an evidence URL; review from `review.html` (see traps); start the bakeoff early; re-derive anything already in the ledger; run another Miskawayh `--adjudicate` round or start Suyuti (both history).

## Evidence

- Measurements + caveats: `TRANSLATION_EXPERIMENTS.md`
- Component contracts: `VERSED_TRANSLATION_ROADMAP.md`
- Sources + rights: `corpus/PD_TRANSLATIONS.md`
- Decisions: `gh issue list --label decision --state all`
- Runs, QE artifacts, alignment output: `~/versed-translator-data/`
- Dashboard (generated): https://bilalghalib.github.io/versed_translator/

## Benchmark gates — deliberately split (2026-08-15)

- **v0.1 — ~300–500 passages, 6–10 genres, human-inspected references.** Answers base-model and architecture questions. That is all it has to do.
- **v1.0 — 2,000–5,000 items, 10+ genres × 4 length bands × 5+ centuries, private holdout, SHA manifest, contamination CI.** Publication-grade. Required **before serious fine-tuning claims**, not before useful experiments.

The master plan's own principle governs: *"Do not optimize for sheer volume. Optimize for coverage and trustworthiness."*
