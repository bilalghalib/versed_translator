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
- **Neural QE cannot be the safety gate.** COMETKiwi 30.4% and item-level MetricX 30.7%. The **block-level MetricX matrix doubled overall detection to 63.4%** by making omission/addition visible (truncation confound retired, 0.73%). It is still blind where it matters: terminology 7.7%, negation 32.6%, agent/patient 40% (n=10), `collapse_paragraphs` a hard 0%. Deterministic checks remain the gate. EXP-20260815-04.
- **MetricX is the only shippable neural signal** (Apache-2.0). COMETKiwi is CC-BY-NC — research mode only, never required by shipping code.
- **Structured blocks work.** Truncation 0.3754 → 0.0073; ID loss is now a run-level metric and caught a live 2.5% omission on first use. Cost: −0.65 chrF. Blocks also make QE ~1.6–2.0× *more expensive* (sub-linear CPU scaling) — the argument for QE on Modal.
- **PD references abridge.** Hitti retains only 40% of Arabic narrator markers. Alignment quality and reference fidelity are different properties, tracked as different fields. Never train isnad handling on these.
- **Alignment from PD translations works.** 39 Baladhuri/Hitti history passages, human-audited **15/15 aligned**, no one-report shift.
- **The whole selected set survived an independent blind re-audit (2026-08-15).** All 81 passages re-verified: **73 aligned / 8 partial / 0 misaligned**; 24/24 sampled rejects genuinely bad, zero over-rejection. The 8 partials are edge jitter only (Ockley ±1 sentence, Blunt half-verse smear, 2 Baladhuri trailing reports) — fix or trim at freeze. EXP-20260815-01.
- **ATHAR's English side is verbatim in-copyright translations** — Rosenthal 1958 and Faris 1952 word-for-word, ~3/4 of pairs with no PD English source in existence; the HF CC labels are legally ineffective (rasaif owned nothing to license) and re-scraping rasaif changes nothing. ATHAR stays `eval_internal` forever; PD alignment is the only rights-clean public reference side. EXP-20260815-01.
- **Miskawayh year-anchor + mandatory adjudication works, at a 20% aligned yield.** 504 proposals, 120 year-spread judged, 24 selected (15/9 across the two bands). 70% came back `partial` — the running-head page lag, caught. Driver: `python -m versed_translator.benchmark.miskawayh_alignment`. Shipping page exists. History is over the 40% cap; do not mine this source further. EXP-20260815-02.
- **Hariri maqama-anchor works, at a 50% aligned yield.** 50/50 sequence-paired, 132 proposals, 103 judged, **37 selected** (17 in 100–250, 20 in 250–600, 26 maqamat). 51 aligned / 52 partial / 0 misaligned / 0 errors. Driver: `python -m versed_translator.benchmark.hariri_alignment`. The all-50 scan still carries Chenery/Steingass synopses; the extractor drops them. Adab/maqama is no longer empty. EXP-20260815-03.
- **Ibn Rushd treatise-anchor does not fill kalam/falsafa.** OpenITI `FaslMaqal` is Fasl+Damima only; Gutenberg Kashf has no Arabic and was left unpaired. 25 proposals, 22 judged, **2 aligned / 20 partial / 0 misaligned**. Interior length cuts smear (Ockley-family). Driver is wired; take is not a genre slice. Do not run another length pass — embeddings if this source is retried, else leave it. EXP-20260815-05.
- **Sources are not the constraint.** Catalog sweep found Miskawayh 383 paragraphs ≥250 words, Suyuti 211, Payne's *Nights* 133–151 per volume × 10. **Usama/Hitti and Biruni/Sachau are staged** (`~/versed-translator-data/benchmark-alignment/recon-usama-biruni.md`). Usama is structurally cuttable (3 abwāb ↔ SECTION I–III, `[N]` ↔ `PageV01PNNN` on the same pagination) but OpenITI `021.BookSUBJ` is **التاريخ** (already over cap) and Hitti is **1929** (US PD via 95-year term as of 2025, not `PD_US_PRE_1930_PUBLICATION`; EU life+70 evidence to 2049 — record only). Biruni science is empty-genre but **not cut-ready**: English `p.N.` is Sachau 1878 Leipzig, PRIMARY Arabic is uncorrected OCR of a 2001 Tehran print. Do not pair those numbers.

## What is running

- Nothing. Usama/Biruni recon finished (off-repo note `~/versed-translator-data/benchmark-alignment/recon-usama-biruni.md`). Ibn Rushd and MetricX readout are in.

## Next 3 things

1. **Human-review the two pending shipping pages, then leave those sources.** Miskawayh: `~/versed-translator-data/benchmark-alignment/miskawayh_eclipse/review_shipping.html` (24 pairs; take is the 9 long-band). Hariri: `~/versed-translator-data/benchmark-alignment/hariri_assemblies/review_shipping.html` (37 pairs; spot-check 10–15). Ibn Rushd's 2 aligned pairs exist at `ibn_rushd_rehman/review_shipping.html` but **do not fill kalam**. **Do not run another Miskawayh, Hariri, or Ibn Rushd length round; skip Suyuti** — history over cap, adab filled, kalam pairing exhausted. Never review from `review.html`.
2. **Keep filling the freeze bar before the bakeoff.** Standing is **81 trusted + 24 Miskawayh pending + 37 Hariri pending**. Need 300–500 trusted and 6–10 genres. **Do not start Usama until the memoir-vs-التاريخ call below is answered.** Do not cut Biruni PRIMARY against Sachau `p.N.` (wrong edition). Next empty genres that are not history/adab: scripture (Palmer Qur'an, strong sura anchors) or a different kalam witness. Then freeze.
3. **Matched-prompt TG12B vs TG27B** on exactly the frozen set, then **one real book**. Do not start Modal until freeze.

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

**One standing, not yet a GitHub issue:** treat Usama/Hitti as **memoir** (first-person *I'tibar*, empty catalog genre, structurally ready) despite OpenITI `021.BookSUBJ = التاريخ`, which is already over the 40% cap? Schema forbids inferring genre from the title. A yes also needs a rights *label* for a 1929 US publication (PD in the US since 2025; not pre-1930); nothing below Opus writes `rights_status`. A no means skip Usama and cut a non-history empty genre (Palmer Qur'an / scripture is the ranked next with real anchors).

`gh issue list --label decision` is otherwise empty; all six from 2026-08-14 are answered and closed.

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

Claude Code usage limits paused mid-sprint; Cursor landed Miskawayh then Hariri. Whoever resumes — read this file top to bottom first, then:

**Done in this Cursor session (do not redo):**
- Miskawayh driver + 24-passage shipping slice (EXP-20260815-02).
- Hariri extractor/driver + 37-passage shipping slice (EXP-20260815-03).
- MetricX block-level matrix readout (EXP-20260815-04).
- Usama/Hitti + Biruni/Sachau staged; recon at `~/versed-translator-data/benchmark-alignment/recon-usama-biruni.md`. **Do not cut Usama until the memoir-vs-history call; do not pair Biruni `p.N.` to OpenITI PageV.**

**Safe anywhere, no credentials (`uv run`):**
- Spot-check shipping pages; regenerate dashboard (`make -f tools/dashboard.mk dashboard`).
- If the Usama call is **yes**: extractor with abwāb↔SECTION + `[N]`↔PageV, macron-collapse on names, assemble Arabic long-band, new rights label only after Opus writes it. If **no**: Palmer Qur'an (scripture, sura/verse headers).
- If Ibn Rushd is retried, embeddings not another length pass.

**Needs credentials (on this Mac, never in the repo):**
- Bilal's eyes on 10–15 Miskawayh shipping pairs **and** 10–15 Hariri shipping pairs. A proposal is not a passage; an `aligned` verdict is not a human audit.
- The Usama memoir-vs-التاريخ + 1929 rights-label call (above).
- Further LLM adjudication (`ANTHROPIC_API_KEY`) — **not for more Miskawayh, Hariri, or Ibn Rushd length cuts**.
- Modal runs (matched-prompt TG12B-vs-27B) — `~/.modal.toml`. **Do not start until the set is frozen.**
- `gh` (decisions live as issues), `ssh nautilus` (OpenITI corpus reads).

**While on pause, do NOT:** freeze below the stop-condition bar; write a rights determination without an evidence URL; review from `review.html`; start the bakeoff early; re-derive ledger facts; run another Miskawayh/Hariri `--adjudicate`; start Suyuti (history) or Payne/Tanukhi (more adab); run another Ibn Rushd length pass; cut Biruni PRIMARY against Sachau page numbers; start Usama as silent extra history.

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
