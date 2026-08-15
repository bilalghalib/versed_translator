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
- **Opus blind re-audit of the 61 shipping pairs is in.** `claude-opus-5`, blind to the Sonnet `aligned` that selected them. Miskawayh **7 aligned / 17 partial** (the empty `end_turn` pair retried at 16k tokens → partial). Hariri **32 aligned / 3 partial / 2 unparseable** (Opus continued Chenery saj' instead of JSON; higher tokens and a JSON-only nudge did not fix it; Opus 5 rejects assistant prefill). **0 misaligned** among parseable replies. Only Opus `aligned` joins the 81: **+39 → 120**. Eval file: `~/versed-translator-data/benchmark-data/v0.1-draft/matched_prompt_eval_120.jsonl`. EXP-20260815-06.
- **Sources are not the constraint.** Catalog sweep found Miskawayh 383 paragraphs ≥250 words, Suyuti 211, Payne's *Nights* 133–151 per volume × 10. **Usama/Hitti and Biruni/Sachau are staged** (`~/versed-translator-data/benchmark-alignment/recon-usama-biruni.md`). Usama is structurally cuttable (3 abwāb ↔ SECTION I–III, `[N]` ↔ `PageV01PNNN` on the same pagination) but OpenITI `021.BookSUBJ` is **التاريخ** (already over cap) and Hitti is **1929** (US PD via 95-year term as of 2025, not `PD_US_PRE_1930_PUBLICATION`; EU life+70 evidence to 2049 — record only). Biruni science is empty-genre but **not cut-ready**: English `p.N.` is Sachau 1878 Leipzig, PRIMARY Arabic is uncorrected OCR of a 2001 Tehran print. Do not pair those numbers.

## What is running

- Nothing. Opus re-audit of the 61 finished (EXP-20260815-06). Eval JSONL for the bakeoff is assembled off-repo.

## Next 3 things

1. **Matched-prompt TG12B vs TG27B** on the 120 (`matched_prompt_eval_120.jsonl`). Same prompt literal recorded (`modal_minimal_v1` vs fidelity — pick one, don't mislabel `v1`). Then one real book.
2. Fine-tune / Isnād A/B/C after the book.
3. Palmer Qur'an extractor is optional and does not gate Modal.

## 🛑 STOP CONDITION FOR BENCHMARK WORK

**Two bars, on purpose:**

- **D2a / Modal gate (now):** contamination-clean PD refs, both length bands, ≥5 materially different registers, honest documented gaps. That is **already true** of the 81 (hadith + history + biography + philosophy + poetry) and is stronger with Hariri's 32 Opus-aligned maqamat. Miskawayh adds only 7 long-history survivors — do not treat the original 24 as trusted. **Proceed to matched-prompt.** The original 300–500 / 6–10 / no-genre-40% line is an **accretion ceiling** — stop adding when we hit it, do not wait for it when sources bounce.
- **v1.0 / fine-tune claims:** 2,000–5,000 items, 10+ genres × 4 bands × 5+ centuries, private holdout, SHA manifest, contamination CI. Required before serious FT claims, not before the bakeoff or the pilot book.

v0.1 still needs rights/provenance metadata and **contamination-clean references** (fresh PD alignments, never ATHAR/rasaif). Those do not relax.

## Human decisions needed

**Default no on Usama** unless you explicitly want a small dual-labelled memoir slice. Skip it: OpenITI says التاريخ (over cap) and 1929 is not pre-1930. Palmer or the bakeoff instead.

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
- **Rhymed PD English can make Opus complete the translation instead of judging.** Two Hariri openings (`m02-a000_001`, `m48-a000_003`) dumped Chenery saj' three times; 16k tokens and a JSON-only nudge did not help; Opus 5 rejects assistant prefill. Unparseable stays out — never default to `aligned`. Do not retry those ids.

## On pause — resuming from Cursor or any other tool (2026-08-15)

Claude Code usage limits paused mid-sprint; Cursor landed Miskawayh then Hariri. Whoever resumes — read this file top to bottom first, then:

**Done in this Cursor session (do not redo):**
- Miskawayh driver + 24-passage shipping slice (EXP-20260815-02).
- Hariri extractor/driver + 37-passage shipping slice (EXP-20260815-03).
- MetricX block-level matrix readout (EXP-20260815-04).
- Usama/Hitti + Biruni/Sachau staged; recon at `~/versed-translator-data/benchmark-alignment/recon-usama-biruni.md`. **Do not cut Usama until the memoir-vs-history call; do not pair Biruni `p.N.` to OpenITI PageV.**
- Opus re-audit of 61 shipping pairs (EXP-20260815-06): **39 survivors**, eval `matched_prompt_eval_120.jsonl`. Do not redo; do not retry the two Hariri saj' dumps.

**Safe anywhere, no credentials (`uv run`):**
- Spot-check shipping pages; regenerate dashboard (`make -f tools/dashboard.mk dashboard`).
- Palmer Qur'an extractor (scripture, sura/verse headers) — cheap extra genre, does not gate Modal.
- If Ibn Rushd is retried, embeddings not another length pass.

**Needs credentials (on this Mac, never in the repo):**
- Matched-prompt TG12B-vs-27B — `~/.modal.toml`. **Unblocked.** Input is `~/versed-translator-data/benchmark-data/v0.1-draft/matched_prompt_eval_120.jsonl`. Record the prompt literal. Oversample long/Hariri. Do not wait for 300–500.
- `gh`, `ssh nautilus`.

**While on pause, do NOT:** pretend v0.1 is v1.0; write a rights determination without evidence; review from `review.html`; start fine-tuning; use ATHAR as gold; mine more history/adab; another Ibn Rushd length pass; cut Biruni PRIMARY against Sachau `p.N.`; start Usama as silent extra history; delay Modal to hunt kalam; treat Sonnet-only Miskawayh as trusted; retry Hariri `m02-a000_001` / `m48-a000_003`.

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
