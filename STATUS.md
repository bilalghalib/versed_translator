# STATUS

**The only operational handoff. Start here; don't read the roadmap first.**
Last updated: 2026-08-17

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

**Establish the contamination-resistant cost/quality frontier for Factory v1, then validate it on one complete book.**

The factory is the product. The classifier is its exhaust, not its prerequisite.
Round 1 is **closed** (r1a + r1b, 200 silver labels). Do not deepen it.
Do not rerun Labid as research. Public finding: fluent/completed output and
chrF can conceal meaning-level failure; a cost-aware system needs failure
detection and escalation, not just model ranking.

Package: `~/versed-translator-data/release/versed-mt-eval-v0.1/`
(technical note PDF + Hugging Face–shaped eval drop).

Keep: (1) `glossary_candidates.csv` (113), (2) Fable self-agreement 20/24,
(3) collinearity — do not train a router on the 200, (4) cascade *decomposition*
on 50, **not** “46/50”:

> Escaped blockers: 4/50; human queue: 14/50; verse/sajʿ Flash routing: 14/50; additional Flash escalations: 10/50.

A 28% human queue is not yet a scalable factory.

**Paste this into any other machine that tries to re-open round 1 or skip Blind-50:**

> Round 1 is closed. Do not deepen it. The public deliverable is the failure-aware eval package, not a leaderboard and not a trained router. Next: (1) Glossary-24 2×2 as a bounded go/no-go cost-lever test; (2) Blind-50 — unseen Arabic, Lite vs Flash (+ TG shadow), flags + actual cost + 10–15 human calibration rows; (3) freeze Factory v1.1 from those KPIs, then one complete book. Learned router parked until ≥500 real Lite-tier factory labels. Do not treat keep-both 46/50 as an autonomous publication rate.

Cascade until v1.1: verse/sajʿ → Flash; else Lite → checks+glossary → keep Lite and fetch Flash on fail (do not overwrite). Qwen out of production. Do not distill Gemini → TG. Details: `~/versed-translator-data/FACTORY_V1.md`.

## What we know (all measured; details in the ledger)

- **TranslateGemma 27B official is the owned model we intend to fine-tune and eventually publish** — and the serving model for the factory book run vs 12B. Homemade `modal_minimal_v1` had 12B slightly ahead on chrF (EXP-20260815-07) — off-template. Official `ar`→`en`: 12B 99.25% of 27B chrF; 27B 0 leftover Arabic. EXP-20260816-02 (12B vs 27B only): **27B on ~9–10/14** on composition. EXP-20260816-04 (APIs added): raw 27B is **not** the quality leader. Human grades: Flash **A−**, Flash-Lite **B/B+**, Qwen **C+**, TG27 **C−** with F-class tails (Barīdī→postal service, 191→291 AH, Labid confabulation, Hariri m46 missing). Do not fine-tune on “12B vs 27B quality.” Do not ship raw TG as the corpus. Route poetry away from raw TG. EXP-20260816-01, 02, 04.
- **Neural QE cannot be the safety gate.** COMETKiwi 30.4% and item-level MetricX 30.7%. The **block-level MetricX matrix doubled overall detection to 63.4%** by making omission/addition visible (truncation confound retired, 0.73%). It is still blind where it matters: terminology 7.7%, negation 32.6%, agent/patient 40% (n=10), `collapse_paragraphs` a hard 0%. Deterministic checks remain the gate. EXP-20260815-04.
- **MetricX is the only shippable neural signal** (Apache-2.0). COMETKiwi is CC-BY-NC — research mode only, never required by shipping code.
- **Structured blocks work.** Truncation 0.3754 → 0.0073; ID loss is now a run-level metric and caught a live 2.5% omission on first use. Cost: −0.65 chrF. Blocks also make QE ~1.6–2.0× *more expensive* (sub-linear CPU scaling) — the argument for QE on Modal.
- **PD references abridge.** Hitti retains only 40% of Arabic narrator markers. Alignment quality and reference fidelity are different properties, tracked as different fields. Never train isnad handling on these.
- **Alignment from PD translations works.** 39 Baladhuri/Hitti history passages, human-audited **15/15 aligned**, no one-report shift.
- **The whole selected set survived an independent blind re-audit (2026-08-15).** All 81 passages re-verified: **73 aligned / 8 partial / 0 misaligned**; 24/24 sampled rejects genuinely bad, zero over-rejection. The 8 partials are edge jitter only (Ockley ±1 sentence, Blunt half-verse smear, 2 Baladhuri trailing reports) — fix or trim at freeze. EXP-20260815-01.
- **ATHAR's English side is verbatim in-copyright translations** — Rosenthal 1958 and Faris 1952 word-for-word, ~3/4 of pairs with no PD English source in existence; the HF CC labels are legally ineffective (rasaif owned nothing to license) and re-scraping rasaif changes nothing. ATHAR stays `eval_internal` as **gold / published-dataset English**. Training on online English (including ATHAR, Ithra, LAL) is an operator choice (`train_ok`); do not ship those strings in a released parallel dataset. EXP-20260815-01.
- **Miskawayh year-anchor + mandatory adjudication works, at a 20% aligned yield.** 504 proposals, 120 year-spread judged, 24 selected (15/9 across the two bands). 70% came back `partial` — the running-head page lag, caught. Driver: `python -m versed_translator.benchmark.miskawayh_alignment`. Shipping page exists. History is over the 40% cap; do not mine this source further. EXP-20260815-02.
- **Hariri maqama-anchor works, at a 50% aligned yield.** 50/50 sequence-paired, 132 proposals, 103 judged, **37 selected** (17 in 100–250, 20 in 250–600, 26 maqamat). 51 aligned / 52 partial / 0 misaligned / 0 errors. Driver: `python -m versed_translator.benchmark.hariri_alignment`. The all-50 scan still carries Chenery/Steingass synopses; the extractor drops them. Adab/maqama is no longer empty. EXP-20260815-03.
- **Ibn Rushd treatise-anchor does not fill kalam/falsafa.** OpenITI `FaslMaqal` is Fasl+Damima only; Gutenberg Kashf has no Arabic and was left unpaired. 25 proposals, 22 judged, **2 aligned / 20 partial / 0 misaligned**. Interior length cuts smear (Ockley-family). Driver is wired; take is not a genre slice. Do not run another length pass — embeddings if this source is retried, else leave it. EXP-20260815-05.
- **Opus blind re-audit of the 61 shipping pairs is in.** `claude-opus-5`, blind to the Sonnet `aligned` that selected them. Miskawayh **7 aligned / 17 partial** (the empty `end_turn` pair retried at 16k tokens → partial). Hariri **32 aligned / 3 partial / 2 unparseable** (Opus continued Chenery saj' instead of JSON; higher tokens and a JSON-only nudge did not fix it; Opus 5 rejects assistant prefill). **0 misaligned** among parseable replies. Only Opus `aligned` joins the 81: **+39 → 120**. Eval file: `~/versed-translator-data/benchmark-data/v0.1-draft/matched_prompt_eval_120.jsonl`. EXP-20260815-06.
- **Matched-prompt 12B vs 27B is in — on the homemade prompt only.** Same blocks, same `modal_minimal_v1`, same H100 / 0.1 / 1536. 12B slightly ahead on chrF and cleaner on truncation. First 27B leg (`structured_blocks_v1`, 17 parse errors) is a side finding, not the comparison. EXP-20260815-07. That bakeoff did **not** use Google's trained chat template.
- **Official-template 12B vs 27B is in, then human-read.** Automatic: 27B +0.33 chrF, 0 vs 5 leftover Arabic, 1.87× GPU. Human (14 passages, Arabic as source of truth, PD English as historical comparator only): scale repairs **composition** (roles, discourse, leakage) before **historical semantics** (`نجوم`→stars on both; al-Barīdī→postal service; Luʾluʾ→Pearl). Compare page: `~/versed-translator-data/benchmark-alignment/official_vs_homemade_compare.html`. EXP-20260816-01 / 02.
- **Qwen-MT and Gemini scored on the same 120 (EXP-20260816-03), then human-read (EXP-20260816-04).** Fair chrF on 115-item overlap: Gemini Flash **47.06**, Flash-Lite 45.80, Qwen-MT 44.78, TG27B official 43.20, TG12B official 42.88. Qwen **663/663**, **0 leftover Arabic** — completeness, not quality. Human 14 (Arabic as truth, two readers): Flash wins every card by a class, not 3.9 chrF points. Flash-Lite is the cheap challenger (held ah325 names; loses `نجوم` anaphor). Qwen is operational fallback / possible restricted-prose route. Note: `كتبت عنه` is Ibn Khallikan 0442, not Hariri m20. Compare: `api_vs_official_compare.html`. Note: `api_14_human_read.md`. Gemini corpus $ unbilled. OpenAI still absent. Contamination untested — next quality experiment is **Blind-50** untranslated OpenITI, no chrF.
- **Fable r1b meaning-level grades invert the chrF ranking (EXP-20260817-01).** Hard half, 25×4, one sitting: Flash **24/25** (only N is empty Labid `v035_051`), Lite **11/25**, TG27B **2/25** (Ḥayy prose), Qwen **0/25**. A 4-chrF-point gap compressed a 24-to-0 publishability gap. Round 1 combined: Flash 48/50, Lite 23/50, TG 2/50, Qwen 0/50. Cascade on 50 is **not** “46/50 autonomous”: escaped 4/50, human queue 14/50, verse Flash 14/50, extra Flash escalations 10/50. Do not replace the flag layer with chrF. Do not train a classifier on these 200. Digest: `fable_r1/DIGEST_r1b.md`. Public package: `release/versed-mt-eval-v0.1/`.
- **Sources are not the constraint.** Catalog sweep found Miskawayh 383 paragraphs ≥250 words, Suyuti 211, Payne's *Nights* 133–151 per volume × 10. **Usama/Hitti and Biruni/Sachau are staged** (`~/versed-translator-data/benchmark-alignment/recon-usama-biruni.md`). Usama is structurally cuttable (3 abwāb ↔ SECTION I–III, `[N]` ↔ `PageV01PNNN` on the same pagination) but OpenITI `021.BookSUBJ` is **التاريخ** (already over cap) and Hitti is **1929** (US PD via 95-year term as of 2025, not `PD_US_PRE_1930_PUBLICATION`; EU life+70 evidence to 2049 — record only). Biruni science is empty-genre but **not cut-ready**: English `p.N.` is Sachau 1878 Leipzig, PRIMARY Arabic is uncorrected OCR of a 2001 Tehran print. Do not pair those numbers.

## What is running

- Nothing on Modal/API. Round 1 frozen. Public eval package staged at `~/versed-translator-data/release/versed-mt-eval-v0.1/`. Glossary-24 not started. Blind-50 not started. Learned router parked until ≥500 Lite-tier factory labels.

## Next 3 things

1. **Glossary-24 2×2** — bounded go/no-go cost-lever test on `glossary_holdout_24.jsonl` (Lite±glossary, Flash±glossary). Predeclared: does Lite+glossary cut TERM/ENTITY blockers and Flash calls enough to be worth the tokens? If Lite stays mediocre, kill the workstream.
2. **Blind-50** — completely unseen Arabic; no English shown in the pipeline; Lite vs Flash (+ TG shadow); same blocking taxonomy; actual cost; 10–15 stratified human calibration rows. This is the book trigger, not the book.
3. **Freeze Factory v1.1** from Blind-50 KPIs (`escaped_rate`, `auto_ship_rate`, `human_queue_rate`, `Flash_calls`, `judge_calls`, `cost_per_arabic_word`), then one complete book. Learned router stays parked until ≥500 real Lite-tier labels.

## 🛑 STOP CONDITION FOR BENCHMARK WORK

**Two bars, on purpose:**

- **D2a / Modal gate (now):** contamination-clean PD refs, both length bands, ≥5 materially different registers, honest documented gaps. That is **already true** of the 81 (hadith + history + biography + philosophy + poetry) and is stronger with Hariri's 32 Opus-aligned maqamat. Miskawayh adds only 7 long-history survivors — do not treat the original 24 as trusted. **Proceed to matched-prompt.** The original 300–500 / 6–10 / no-genre-40% line is an **accretion ceiling** — stop adding when we hit it, do not wait for it when sources bounce.
- **v1.0 / fine-tune claims:** 2,000–5,000 items, 10+ genres × 4 bands × 5+ centuries, private holdout, SHA manifest, contamination CI. Required before serious FT claims, not before the bakeoff or the pilot book.

v0.1 still needs rights/provenance metadata and **contamination-clean references** (fresh PD alignments, never ATHAR/rasaif). Those do not relax.

## Human decisions needed

**Default no on Usama as extra benchmark history.** Rights: **US public domain as of 2025** (Hitti 1929, 95-year term). Bilal 2026-08-16: US citizen, US law is the rights rule. EU life+70 is not the gate for this project. Still do not silently add Usama as more التاريخ beyond the genre cap — that is a factory/benchmark call, not a rights call.

**Insert Qwen-MT + Gemini on the frozen 120 before the book?** **Done** (EXP-20260816-03 / 04). Remaining human work: 10–15 Blind-50 calibration rows when that experiment runs; dad queue deferred. Do not treat chrF-vs-PD or 0 leftover Arabic as quality. Do not FT TG on Gemini outputs. Gemini/Fable texts stay `train_eligible=false`. The book waits on Blind-50, not the other way around.

`gh issue list --label decision` is otherwise empty; all six from 2026-08-14 are answered and closed.

The one standing ask, when the small benchmark exists: **label passages** "would a competent bilingual editor find a substantive error?"

⚠️ The invariant to protect is narrow: **no threshold fitting on the samples used to claim router performance.** Designate a disjoint calibration subset *when Versed-QE is actually calibrated*, keeping an untouched evaluation slice. v0.1's primary job is model and architecture selection — do **not** pre-split it into two frozen halves now.

## Known traps — do not re-derive

- A full row count, clean exit code and populated output file are **all compatible with total failure**. A 139-row run was 139 connection errors; the tell was `wall_s: 0.06`. Check the error field *and* a plausibility signal.
- **A metadata label is not evidence.** Both Modal legs recorded `prompt_template_id: "v1"` while sending something else; the bakeoff's headline comparison was confounded for a day and nothing failed.
- `nohup … & disown` does not survive session teardown, and **`setsid` does not exist on macOS**. Use `subprocess.Popen(..., start_new_session=True)` locally, `modal run --detach` for Modal, and write a `done-<job>` sentinel with the exit code.
- vLLM 0.11.0 allows `transformers` 5.x, which renamed `rope_scaling`. Pin `transformers<5`. Patching the model's `config.json` does **not** help — three attempts proved it, and a stale comment claiming otherwise was corrected.
- Sonnet 5's `max_tokens` caps thinking **plus** text; too small a budget returns empty translations.
- **Gemini OpenAI-compat has the same trap:** `max_tokens: 16` on `gemini-flash-latest` returned HTTP 200 with `completion_tokens: 0` and no `message.content` (thinking ate the budget). Native `generateContent` was fine. Do not treat HTTP 200 as a translation. Default harness `max_tokens=4096` is the safer openai_compat setting; confirm on a 1-item probe before a 663-block run.
- Local CPU inference for a 12B is ~2 tok/s. Inference happens on Modal.
- `/Volumes/hikma` (SMB) degrades mid-session to permission-denied at the share root. Read the corpus via `ssh nautilus` (`/mnt/hikma`).
- PDF rendering needs Homebrew's GTK stack: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib GI_TYPELIB_PATH=/opt/homebrew/lib/girepository-1.0 ~/mambaforge/bin/python`. Verify Arabic output **visually** — PyMuPDF `get_text()` returns visual order for RTL, so broken and correct look alike.
- **`review.html` is triage, not the benchmark** — all proposals, worst-first, rejects included. Reading it as the shipped set has caused a false "alignment is broken" alarm **twice** (Baladhuri, then 2026-08-15). Humans review `review_shipping.html` (selected-only, best-first); every source must generate both.
- **Model tier ∝ blast radius, not text difficulty.** Volume work (OCR cleanup, tagging, dedup) → cheap models in parallel; propagating decisions (rights calls, adjudication verdicts, benchmark verification) → top tier with thinking budget. Nothing below top tier writes a rights determination.
- **Rhymed PD English can make Opus complete the translation instead of judging.** Two Hariri openings (`m02-a000_001`, `m48-a000_003`) dumped Chenery saj' three times; 16k tokens and a JSON-only nudge did not help; Opus 5 rejects assistant prefill. Unparseable stays out — never default to `aligned`. Do not retry those ids.
- **A structured probe that returns English is not a held JSON contract.** 27B's first matched-prompt leg hit `TemplateError` then still parsed four probe blocks, so `probe_ok` green-lit `structured_blocks_v1` against 12B's `modal_minimal_v1`. `structured_probe_held` now treats chat-template incompatibility as failure. Do not score that first 27B file as matched.

## On pause — resuming from Cursor or any other tool (2026-08-15)

Claude Code usage limits paused mid-sprint; Cursor landed Miskawayh then Hariri. Whoever resumes — read this file top to bottom first, then:

**Done in this Cursor session (do not redo):**
- Miskawayh driver + 24-passage shipping slice (EXP-20260815-02).
- Hariri extractor/driver + 37-passage shipping slice (EXP-20260815-03).
- MetricX block-level matrix readout (EXP-20260815-04).
- Usama/Hitti + Biruni/Sachau staged; recon at `~/versed-translator-data/benchmark-alignment/recon-usama-biruni.md`. **Do not cut Usama until the memoir-vs-history call; do not pair Biruni `p.N.` to OpenITI PageV.**
- Opus re-audit of 61 shipping pairs (EXP-20260815-06): **39 survivors**, eval `matched_prompt_eval_120.jsonl`. Do not redo; do not retry the two Hariri saj' dumps.
- Matched-prompt 12B vs 27B (EXP-20260815-07). Do not score the first 27B structured file as matched.
- Official-template 12B vs 27B (EXP-20260816-01). Do not overwrite the homemade numbers.
- Human read of the 14-passage official sample (EXP-20260816-02). Serving model is 27B. Do not fine-tune on 12-vs-27 quality.
- Qwen-MT + Gemini Flash/Lite on the frozen 120 (EXP-20260816-03). Do not treat chrF-vs-PD or 0 leftover Arabic as quality.
- Human Arabic-first read of the API 14 (EXP-20260816-04). Flash is the quality leader; Flash-Lite the cheap challenger; Qwen operational fallback; TG27 owned/FT target, not corpus quality leader. Do not attribute `كتبت عنه` to Hariri m20 (it is Ibn Khallikan 0442).
- Factory v1 decided 2026-08-16 (`FACTORY_V1.md`). Fable r1 CSV exported (50×4, 14 excluded). Round 1 is closed: r1a + r1b = 200 silver rows (EXP-20260816-06, EXP-20260817-01), not a routing decision. Cascade + glossary retrieve live in `versed_translator.factory`; policy sim on 50 in `fable_r1/policy_sim_r1.json` (keep-both 46/50). Do not train a learned source-router on these 200. Do not distill Gemini→TG. Empty Labid (`blunt_odes:labid-v035_051`) is a generation miss, not a translation; `check_output` now flags `nan`/empty as MISSING.
- Public PD English texts are on disk and recorded in `translation_files`. **23/23 public editions have a local file** (added Sale Qur'an Gutenberg, Sprenger Masʿudi 1841, Field Munqidh Gutenberg 58977, Sachau *India* v1–v2). IA `/download/` still 500s; fetch falls back to `/cors/`. India vol. 1 preface cites *Chronology of Ancient Nations* — that is not the wrong book. Do not cut Usama / Biruni Chronology / Payne / Tanukhi / Seelye / Lee / Lyall-1930-anthology into the benchmark from this fetch.
- **Two English buckets (2026-08-17):** train on any **public GET without login** (`train_ok`) — year does not matter. Published dataset = US PD (title-page 1930 or earlier / 95-year term) or CC0/BY/BY-SA (`redistribute_ok`). Do not mix train-english into pd-english. Train-only now includes Ithra 2020, Arberry 1957 + Ring of the Dove HTML, Faris 1952, al-islam Nahj/Sahifa/Mizan 1–6/Saduq (Uyun, Khisal, Kamal, Fyzee creed + Safi Hasan Essence)/Mufid (Amali, Tashih)/Tusi (Ghayba; Tenets booklet not joined to Iqtisad)/Nu'mani Ghayba/Tabarsi Mishkat + I'lam al-Wara (Beacons of Light, partial)/Askari tafsir (attribution contested)/Hilli Kashf al-Yaqin/Ibn Tawus Lohoof/Ibn Qulawayh Kamil al-Ziyarat/Shahid Thani (Musakkin al-Fu'ad, Kashf al-Riba), Ivry/Genequand/Fulton/Watt. Public now also includes Miller 1928 Bab al-Hadi 'Ashar. LAL English is still a drop slot. Login walls: `corpus/login_walls.json`. Yield per pass: `corpus/harvest_log.json`.
- **Align to OpenITI by spine, not title.** Page-level only works when English and Arabic share a unit: maqama title (Hariri, now Hamadhani), sura/ayah (Palmer + Rodwell — Rodwell print order is chronological), Anbari ode number (Mufaddaliyat), year/page-in-edition (Miskawayh, Usama), named chapter (Faris idols if dropped). Lee Battuta is an abridgement; Lyall 1930 is a mixed-poet anthology (no single URI); Hamilton Gutenberg is one volume of a long sira; Baydawi is Sura III only. Catalog URI is necessary and not sufficient.

**Safe anywhere, no credentials (`uv run`):**
- Spot-check shipping pages; regenerate dashboard (`make -f tools/dashboard.mk dashboard`).
- Palmer Qur'an extractor (scripture, sura/verse headers) — cheap extra genre, does not gate Modal.
- Re-fetch public PD English (idempotent): `python -m versed_translator.corpus.inventory --fetch-pd-english`.
- Re-fetch train-only English (idempotent): `python -m versed_translator.corpus.inventory --fetch-train-english`.
- Extract Ithra/Johnson English slices: `python -m versed_translator.corpus.extract_train`.
- If Ibn Rushd is retried, embeddings not another length pass.

**Needs credentials (on this Mac, never in the repo):**
- One real book on 27B / official template — `~/.modal.toml`. Do not wait for 300–500.
- API bakeoff **done** (EXP-20260816-03). Keys stay in gitignored `.env`. Never commit; this repo is public.
- `gh`, `ssh nautilus`.

**While on pause, do NOT:** pretend v0.1 is v1.0; write a rights determination without evidence; review from `review.html`; start fine-tuning (including a 12-vs-27 quality FT or Gemini→TG distill); use ATHAR as gold; mine more history/adab; another Ibn Rushd length pass; cut Biruni PRIMARY against Sachau `p.N.`; start Usama as silent extra history; delay Modal to hunt kalam; treat Sonnet-only Miskawayh as trusted; retry Hariri `m02-a000_001` / `m48-a000_003`; score a homemade-prompt file as official; serve the book on `modal_minimal_v1` or treat chrF-vs-PD as the quality gate; treat Qwen 120/120 as a quality win; publish raw TG as the corpus; train a learned router before the invariants checker; reopen r1a or r1b or train a publishable-classifier on the 200 Fable rows; spend corpus-scale Gemini money before Blind-50; paste API keys into chat, commits, or the ground-truth packet.

## Evidence

- Measurements + caveats: `TRANSLATION_EXPERIMENTS.md`
- Sendable measured-facts packet: `~/versed-translator-data/GROUND_TRUTH_EXPERIMENTS.md`
- Shareable research report (this sprint): `~/versed-translator-data/RESEARCH_REPORT_2026-08-16.md`
- Factory v1 (decided): `~/versed-translator-data/FACTORY_V1.md`
- Fable r1 CSVs: `~/versed-translator-data/benchmark-alignment/fable_r1/`
- Public eval package: `~/versed-translator-data/release/versed-mt-eval-v0.1/`
- Component contracts: `VERSED_TRANSLATION_ROADMAP.md`
- Sources + rights: `corpus/PD_TRANSLATIONS.md`
- Decisions: `gh issue list --label decision --state all`
- Runs, QE artifacts, alignment output: `~/versed-translator-data/` (`VERSED_DATA`; see `versed_translator.paths`)

## Where the three "versed" paths are

They are not copies of each other:

| Path | What it is |
| --- | --- |
| `~/Projects/scripts/versed_translator` | Git repo: code, tests, STATUS, ledger |
| `…/src/versed_translator/` | Python package inside that repo (src layout) |
| `~/versed-translator-data` | Off-repo data: Fable CSVs, runs, PD texts, reports |

Override the data root with `VERSED_DATA`. Hikma/OpenITI stay on the share.
- Dashboard (generated): https://bilalghalib.github.io/versed_translator/

## Benchmark gates — deliberately split (2026-08-15)

- **v0.1 — ~300–500 passages, 6–10 genres, human-inspected references.** Answers base-model and architecture questions. That is all it has to do.
- **v1.0 — 2,000–5,000 items, 10+ genres × 4 length bands × 5+ centuries, private holdout, SHA manifest, contamination CI.** Publication-grade. Required **before serious fine-tuning claims**, not before useful experiments.

The master plan's own principle governs: *"Do not optimize for sheer volume. Optimize for coverage and trustworthiness."*
