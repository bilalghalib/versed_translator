# VERSED_TRANSLATION_ROADMAP.md

**Component contracts only. This is NOT the handoff and NOT a status board.**

→ **Start at `STATUS.md`.** It carries current state, what's running, next steps, and open decisions.
→ **Numbers live in `TRANSLATION_EXPERIMENTS.md`**, with their caveats attached. Results were being written in both places; the ledger is canonical.
→ **Decisions are GitHub issues** labelled `decision` (`gh issue list --label decision --state all`). `decisions.json` was deleted 2026-08-15 — maintaining two decision stores by hand was a synchronization tax with no benefit.

What this file is for: each component C0–C12 has an **END STATE** written to be verifiable — a concrete condition plus a `Verify:` check — so an agent can tell when it is actually done. That is the part worth keeping.

**Standing rules (violations are bugs):**
- The frozen benchmark never enters training data, synthetic-generation pools, or retrieval indexes.
- Translator and evaluator are always separate systems.
- Every artifact carries provenance + rights fields from birth.
- Prompts, thresholds, and model IDs are versioned; any change bumps a version.
- Estimates are placeholders until measured; never present them as measurements.
- In the `versed` repo, obey `CURRENT_PIPELINE_CONTRACT.md`.

---

## How this document is worked

Each component below has an **END STATE** written to be *verifiable* — a concrete condition plus a `Verify:` check. The operating loop for agent sessions (Fable or otherwise):

1. Pick the highest-leverage component whose dependencies are met.
2. Iterate — implement, measure, fix — until `Verify:` passes. Don't ask permission for steps tagged **[AGENT]**.
3. Stop at **[HUMAN]** gates (money, rights, taste, outreach, irreversible publication) and queue the decision with the evidence attached.
4. Update the component's STATUS block and `TRANSLATION_EXPERIMENTS.md`. Never edit a frozen artifact.

Tags: **[AGENT]** = machine-verifiable, iterate autonomously. **[HUMAN]** = Bilal decides. Decision points are numbered `D*` and collected in §Decision queue.

**Standing rules (violations are bugs):**
- The frozen benchmark never enters training data, synthetic-generation pools, or retrieval indexes. The contamination check is a CI gate.
- Translator and evaluator are always separate systems.
- Every artifact (benchmark item, training pair, translation, audio) carries provenance + rights fields from birth.
- Prompts, thresholds, and model IDs are versioned; any change bumps a version.
- Estimates from the planning conversation (costs, throughput) are placeholders until measured; never present them as measurements.
- In the `versed` repo, obey `CURRENT_PIPELINE_CONTRACT.md` (VPS owns the queue, Modal is an adapter, no new tables unless replacing, idempotent migrations).

## Two repos, one system

```
versed_translator (this repo — the LAB)          versed (the FACTORY)
├─ benchmark/   frozen eval sets                 ├─ OpenITI ingest → v2 graph        [exists]
├─ harness/     run any translator, same I/O     ├─ VPS worker, queues, ledger       [exists]
├─ qe/          QE eval + Versed-QE router       ├─ Modal adapters (audio, models)   [exists]
├─ align/       Versed Align engine              ├─ Reader + provenance labels       [partial]
├─ corpus/      rights inventory + Versed        ├─ Audio pipeline (Ar done,
│               Parallel + training sets         │   En = later derivative)          [exists]
└─ throughput/  Modal serving + cost grids       └─ /openiti-ops dashboard           [exists]

Lab → Factory interfaces: (a) chosen model + serving config, (b) versed_qe package,
(c) versed_align package, (d) benchmark releases, (e) translation editions written
through existing producer/consumer paths. The factory never depends on lab internals.
```

---

# Component end states

## C0 — Lab repo stood up

**END STATE:** `bilalghalib/versed_translator` on GitHub; Python project (uv-managed) with `benchmark/ harness/ qe/ align/ corpus/ throughput/ docs/`; CI running lint + tests green; the four root docs committed; secrets only via `.env` (gitignored); Modal profile pinned in config.
**Verify:** `gh repo view bilalghalib/versed_translator` succeeds; CI green on main; `uv run pytest` passes.

Checkpoints:
1. [AGENT] git init, docs committed, private repo created and pushed. *(done 2026-08-12)*
2. [AGENT] Scaffold package layout + CI. *(done 2026-08-12 — src/versed_translator with 6 subpackages, stub CLIs, 10 smoke tests, ruff, GH Actions)*
3. [AGENT] Status dashboard: `tools/build_dashboard.py` (stdlib-only) parses this doc + experiments ledger + git log → self-contained `docs/index.html`. Live at **https://bilalghalib.github.io/versed_translator/** (GitHub Pages from `main:/docs` — refreshes on every push) with a tailnet copy at `/Volumes/hikma/versed-translator/dashboard/index.html` (refresh via `tools/deploy_dashboard.sh`). Rebuild after any status change: `make -f tools/dashboard.mk dashboard`, commit, push. *(done 2026-08-12; note: versed.wayway.ai routes straight to the uvicorn worker app, so no static path exists there without touching factory code — hence Pages)*
4. ~~GitHub Actions billing-blocked~~ → resolved by D0: public repos get free Actions. *(2026-08-12)*
5. **D0 — DECIDED 2026-08-12: public.** Sensitive material scrubbed before the flip (private strategy conversation removed from the tree; server/network identifiers redacted; git history squashed). Benchmark contamination policy (D1c) still applies: the held-out split never enters this repo.

Workspace (see `src/versed_translator/paths.py`, env-overridable):
- `/Volumes/Nodes/versed-translator/{scratch,models,corpus-cache}` — local fast disk (2.0TB free).
- `/Volumes/hikma/versed-translator/` — 11TB network share (nautilus via Tailscale), also mounted on the wayway server at `/mnt/hikma`. **OpenITI corpus already present at `/Volumes/hikma/OpenITI`.** Quirk: the local SMB mount cannot create dirs at share root — create dirs via `ssh wayway`.

**STATUS:** COMPLETE 2026-08-12 — repo public, CI free, scaffold green, dashboard live at bilalghalib.github.io/versed_translator.
**NEXT DEPENDENCY:** none. C1 and C6 are unblocked. Model acquisition prep: quantized TranslateGemma 12B/4B already in local Ollama (dev use); full-precision `google/translategemma-{27b,12b,4b}-it` are **gated on HF — [HUMAN] accept the license once** on each model page (account: bilalghalib), then `tools/fetch_models.sh` archives them to local scratch + hikma.

---

## C1 — Versed Benchmark v0.1 (frozen)

**END STATE:** Immutable tagged release `benchmark-v0.1`: 2,000–5,000 items with the master-plan item schema; coverage ≥10 genres × 4 length bands × ≥5 centuries; every item has explicit `rights_status` with an evidence pointer; loader + stats CLI; SHA-256 manifest; a **private held-out split (~20–40%)** stored outside the public repo; `check-contamination` tool that any training-set assembly must call.
**Verify:** `uv run versed-benchmark stats v0.1` meets coverage minimums; manifest hash reproducible; contamination tool returns a report on a toy dataset; held-out split absent from public tree.

Sequencing insight: **v0.1 uses only pre-aligned sources** (ATHAR, LK Hadith, curated Ormsby excerpts, hand-checked Wikisource passages). Alignment-engine-derived items wait for C7 → they become v0.2 expansion. This unblocks the bakeoff months earlier.

Checkpoints:
1. [AGENT] ~~Source acquisition + per-source rights ledger~~ **done 2026-08-12** — loaders + `corpus/rights_ledger.json` with verbatim license quotes; measured: **ATHAR 66,043** pairs (65,043 train + 1,000 native test — preserve their split), **LK Hadith 33,845** (README claims 39,038 — real CSVs are ~13% short), **hadith-json 47,317** usable pairs (al-Darimi has zero English; english is INDEX_ONLY per D6c). ✅ **ATHAR license — RESOLVED 2026-08-14 (D1d): MIT / commercially usable**, by provenance research rather than an author email. `Kandil7/Athar-Datasets` (created April 2026) carries HF structured `license: mit` **and** prose explicitly permitting commercial use. The "research and personal use" prose survives only in the later Shamela4 repos (`AuthenticIlm/Shamela4_Full_DB` extracted 2026-04-26; `Kandil7/Athar-Shamela4` duplicated 2026-06-02) — which *also* carry `license: mit` in structured metadata, so the best reading is stale prose left in place while the repo-level license was set independently. **Honest limit:** no commit documenting a license change was found; this is a well-supported inference, not documentary proof. **Carve-out in force:** MIT cannot grant copyright the dataset creator doesn't own — modern editor introductions (مقدمة المحقق) and modern commentary must be filtered; the ancient source text is what we rely on (Shamela4's `is_hidden: true` copyright/access flag is consistent with this). ATHAR moves off `eval_internal` for C8 subject to that filter. ⚠️ **Length-band gap**: ATHAR median is 18 Arabic words — sentence-level; the 100–250/250–600 bands must come from PD-translation alignment or curation, not ATHAR.
2. [AGENT] Normalization + stratified sampling to coverage targets; passage-size banding (30–80 / 100–250 / 250–600 / near-context-limit). Longer bands depend on PD sources (see `corpus/PD_TRANSLATIONS.md`: 16 seed works; strongest for early alignment: Baladhuri/Hitti, Ibn Khallikan/de Slane, Hariri/Chenery+Steingass).

**D1e DECIDED 2026-08-14 → option (d): targeted passage alignment from the PD list, benchmark-scale only.** Not waiting for C7 — a benchmark needs a few hundred aligned passages, not whole aligned books.

Decisions:
- **D1a** [HUMAN ratifies] Archaic PD translations stay in as references with a `register:archaic` flag (recommended — QE analysis needs them) vs. excluded.
- **D1b** [AGENT proposes] Small experimental poetry subset in v0.1 (recommended) vs. defer.
- **D1c** [HUMAN] Publication policy: publish the rights-safe split with canary strings; keep held-out split private permanently (recommended). Decides with D0.
- **D1e** [HUMAN] **Genre-coverage fork** (2026-08-14 — the draft is 99.6% hadith and ATHAR cannot fix it as-is, see START HERE correction). Options:
  - **(a)** Email the ATHAR author for per-work/genre provenance (combine with the D1d license question — one email, two unlocks). Recommended first move; costs nothing.
  - **(b)** Interim: add a sub-30-word band so ATHAR's sentence-level diversity counts, accepting coarse genre labels until (a) answers.
  - **(c)** Accept v0.1-draft as hadith-only (every result already labeled so) and get genre via PD-translation alignment — this pulls C7 forward and is a genuinely bigger scope; take it deliberately as the v0.2 path, never by drift.

### D1e option (d) — FIRST VERTICAL SLICE SHIPPED 2026-08-14: al-Baladhuri / Hitti

One work, end to end. Code: `src/versed_translator/benchmark/sources/{openiti_markdown,translit,hitti_ocr,baladhuri,llm_adjudicator}.py`, driven by `versed_translator.benchmark.pd_alignment`. Repo-tracked output (no text): `benchmark/alignment/baladhuri_hitti/`. Text + the [HUMAN] review page live at `~/versed-translator-data/benchmark-alignment/baladhuri_hitti/`.

**Why Baladhuri and not Hariri**, which the verification block ranked #1: the criterion that decides a first slice is *bilateral* structure, and Baladhuri/Hitti is the only candidate with three layers of it. (1) 90 Arabic `### |` sections against 70 Hitti Part/Chapter units whose titles transliterate the Arabic ones. (2) Baladhuri is a chain of **akhbar**, each opening with an isnad, and Hitti keeps one paragraph per khabar with the isnad abridged to first + last authority (his own footnote, p. 16) — so the *transmitter names* are shared between the two scripts and give a **checkable** anchor. (3) A passage bracketed by a matched name at each end cannot be off-by-one. Hariri's 50 maqamat are single anchors per unit with nothing inside them, and each maqama is far longer than the target bands, so sub-unit alignment there would have been LLM guesswork with no way to check it. Genre also decided it: `021.BookSUBJ` = التاريخ (history), absent from v0.1-draft entirely.

**Yield:** 90 sections → 39 confirmed section↔chapter pairs → 199 khabar-level cuts → 109 assembled passages → **39 selected** (30 in 100–250, 9 in 250–600, across 20 chapters; 21 `structural`, 18 `llm_proposed`).

**Findings worth carrying forward:**

1. **Transliteration anchors work far better than expected.** Romanising Arabic to the same digraph spellings the English uses, then deleting vowels/w/y/hamza from both sides, matched 23/23 hand-checked name pairs. `translit.py`.
2. **Titles alone are not enough, and failing on them is invisible.** Matching Arabic section titles to English chapter titles put ذكر حفائر مكة against "The Floods in Makkah" — Hitti *translates* half his titles, so the only shared word is the place name, which the adjacent chapter also has. Fixed by scoring candidates on khabar-level cut counts, not titles. **Every downstream count looked right while it was wrong.**
3. **A cut must be tested head-against-head.** Matching English names anywhere in an Arabic paragraph, or merely near its start, both produced passages whose Arabic began one khabar before the English — at word ratios of 1.3–1.5, i.e. exactly the healthy-looking number a shifted alignment gives.
4. **Length ratio is a usable filter once calibrated, and worthless before.** All 109 passages were audited by LLM: fully-parallel ones run 1.13–1.82 (median 1.49), partial ones 0.43–2.68 (median 1.07). Narrowing from a guessed 0.85–2.30 to 1.05–1.95 raised the fully-parallel rate above 0.8 structural confidence from 80% to 87%.
5. **Structural confidence is genuinely calibrated:** ≥0.9 → 91% fully parallel, 0.8–0.9 → 76%, <0.7 → 22%. **Zero passages in 109 were grossly misaligned**; the failure mode is partial overlap, not shift.
6. **The long band is the expensive one.** 250–600 yields ~9 usable passages per work, against ~30 for 100–250: longer spans are likelier to contain a footnote and likelier to hit one of Hitti's omissions. **Closing the benchmark's 250–600 gap needs 3–4 PD works, not one.**
7. **OCR apparatus is the residual quality ceiling**, not alignment. 13 of 109 passages carry a footnote fused into a body sentence. They are flagged and excluded rather than excised — a regex confident enough to cut them is confident enough to cut real prose.

**STATUS:** ACTIVE — checkpoints 1–2 done at draft level (v0.1-draft: 1,111 draft_test + 139 dev_bakeoff, assembly deterministic); **not frozen**. D1e option (d) has a working first slice (39 history passages); genre coverage still needs more works. Checkpoint 3 ([HUMAN] spot audit) is now unblocked for this slice — the review page is built and waiting.
**NEXT DEPENDENCY (first slice):** DONE — 15 Baladhuri items human-audited, then three additional PD works generated below.

### D1e option (d) — SECOND MACHINE-GATED TRANCHE 2026-08-14

Three more works are now extracted end to end. Full text and review pages remain off-repo; text-free manifests/reports live under `benchmark/alignment/`.

- **Ibn Khallikan / de Slane (biography): 21 selected** — 10 in 100–250, 11 in 250–600. This OpenITI witness has **862** `$BIO_*` headings (not the 946 claimed in the earlier handoff). Romanised English headings matched 169 entries structurally; abnormal spans were removed, then 30 whole-biography candidates were content-adjudicated: 21 aligned, 9 partial. `reference_fidelity` remains pending human audit.
- **Blunt's Seven Golden Odes (poetry): 14 selected** — 7+7. The Arabic commentary was excluded by taking only the first verse under each numbered section. All seven poems resolve to 594 Arabic and 594 English verse units after monotone OCR-fragment repair. Of 26 non-overlapping passage proposals, 14 were content-aligned and 12 partial.
- **Ockley's Hayy (philosophy): 7 selected** — 3+4. The clean English OCR did **not** make length alignment reliable: 120 numbered English sections against 492 Arabic paragraphs yielded 50 in-range proposals, but only one contiguous island (English sections 22–38) produced seven aligned passages. The rest were partial/misaligned and are excluded. This is strong negative evidence against treating clean OCR or healthy ratios as boundary evidence.

**STATUS:** 81 machine-gated passages across four works (39 Baladhuri + 42 new); 15 human-audited. The new 42 remain candidates, not benchmark gold.
**NEXT DEPENDENCY:** [HUMAN] review the three new review pages, prioritising the 21 selected Ibn Khallikan biographies and all 7 Ockley survivors; then add at least one more bilaterally anchored work to close the ~100-item human-audit target. Hariri remains the strongest next genre, but needs in-text maqama anchors rather than `### |` headings.

---

## C2 — Translation harness + bakeoff

**END STATE:** `versed-harness run --model <id> --benchmark v0.1` emits standardized JSONL (master-plan run schema: model, version, quantization, prompt template id, tokens, latency, cost, translation) for **every** candidate: TranslateGemma 27B, TranslateGemma 12B, Qwen-MT, Gemini Flash tier, DeepSeek V4, one frontier ceiling, plus the current-versed Claude few-shot-Ormsby configuration as continuity baseline. ID-preserving structured block output (`[{"id":"AR_001","english":...}]`) is tested, and ID-loss counts as an error metric. A comparison report by genre × length × error category exists, and the baseline-translator DECISION is recorded.
**Verify:** all candidate rows present in `harness/reports/bakeoff-v1.md`; every run JSONL validates; D2a filled in.

Checkpoints:
1. [AGENT] Harness core + versioned prompt registry (seed prompts from `local_translation/prompts.py` fidelity rules + few-shot-Ormsby finding).
2. [AGENT] API adapters. **Keys provisioned 2026-08-14 (D2c): DeepSeek + Qwen/DashScope, both smoke-verified live.** Gemini/OpenAI still absent → those legs stay descoped. Keys live in gitignored `.env` (mode 600) — **never commit them; this repo is public.** Verified working config, so the bakeoff need not rediscover it:
   - DeepSeek — `https://api.deepseek.com/chat/completions`, model `deepseek-chat`, `Authorization: Bearer $DEEPSEEK_API_KEY`.
   - Qwen-MT — `https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions` (the **intl** host), model `qwen-mt-turbo`, `$QWEN_API_KEY`. Qwen-MT is a dedicated translation model: it takes `translation_options: {source_lang, target_lang}` and no system prompt, so the harness's prompt-template axis does not apply to it the way it does to the others — record its template id as its own value rather than pretending it ran `v1`.
3. [AGENT] Modal vLLM/SGLang adapter serving TranslateGemma 27B/12B (verify current model availability/versions at execution time; also becomes C3's serving path).
4. [HUMAN] **D2b — spend cap** for the full bakeoff (rough placeholder: $100–250 API + $50–150 GPU; replace with measured).
5. [AGENT] Full run + scoring (reference-based metrics where references exist; C4 QE scores attached later) + report.
6. [AGENT] Close versed `ACTIVE_RUN` Cut 5 by reference to this report (one bakeoff, not two divergent ones).

Decisions:
- **D2a** [HUMAN ratifies AGENT recommendation] Baseline production translator + measured 12B↔27B gap. **Largely forced (2026-08-14 insight):** C8 requires an open, fine-tunable base — Gemini/DeepSeek-API/Qwen-MT-API cannot be it regardless of score. TG27B is the only serious open MT candidate in the field and just tied the frontier ceiling on hadith at 36× the speed. The missing provider legs answer a *different* question (pure-API corpus-route cost), which only matters if fine-tuning fails at D8a. The one leg still genuinely needed: **TG12B on Modal** (12B↔27B gap drives economics; never measured).
- **D2c** [HUMAN] Provision Gemini/Qwen/DeepSeek keys **or** formally descope the bakeoff field to TG27B/TG12B + Claude ceiling, recording D2a as decided-by-field. Either is fine; carrying "no keys" as ambient blockage is not.
- **D2e** [HUMAN ratifies] **Structured block translation with ID preservation as the production contract.** Dissolves the C5 known gap (partial clause removal on unpunctuated classical Arabic — invisible to both COMETKiwi and deterministic checks from (source, output) alone; a dropped block is directly observable). Harness already supports it. One-line architectural decision, cheaper than any detection scheme.

**STATUS:** ACTIVE — harness + scoring built; dev_bakeoff (139 items, hadith-only) measured for Sonnet 5 and TG27B; TG12B Modal leg pending; full bakeoff blocked on C1 freeze (D2c was decided 2026-08-14: keys — DeepSeek + Qwen live, Gemini/OpenAI descoped).
**NEXT DEPENDENCY:** D2c (keys-or-descope); C1 frozen for the real run.

---

## C3 — Measured serving economics

**END STATE:** Reproducible `throughput/` Modal scripts; measured **saturated** throughput for the chosen open model on ≥2 GPU configs (start 1×H100, add 2×/4× if scaling justifies) across concurrency {1..512} × source length {128..1024+}; BF16 vs FP8 quality delta measured on a benchmark subset; a one-page cost model in **$/M Arabic words end-to-end**, with a whole-corpus (~2B word) projection carrying explicit error bars.
**Verify:** `throughput/results/*.json` grid complete; cost table in report; D3a recorded. The hypothetical 22k tok/s figure is either confirmed, corrected, or retired.

Decisions:
- **D3a** [HUMAN ratifies] Production serving config. FP8 acceptable only if benchmark metrics drop <0.5% relative and C4 adversarial detection is unchanged.
- **D3b** [HUMAN] GPU spend cap for the grid (placeholder $100–300).

**STATUS:** NOT STARTED.
**NEXT DEPENDENCY:** C2 checkpoint 3 (serving adapter).

---

## C4 — QE truth study (existing systems + adversarial suite)

**END STATE:** MetricX-QE + COMETKiwi (+ any clearly superior current QE found at execution time — pin exact versions) scored over **all** C2 outputs; an error-injection suite implementing all 15 master-plan corruption types, each injector unit-tested to provably produce its intended corruption; a detection matrix (error type × QE system → sensitivity curves); a written verdict on Classical-Arabic blind spots.
**Verify:** `qe/reports/detection_matrix.{json,md}` covers 15/15 error types; every C2 run row carries QE scores; verdict section non-empty.

Model access (verified 2026-08-13): **COMETKiwi** (`Unbabel/wmt22-cometkiwi-da`) gated access granted, downloads fine — but it is **CC-BY-NC-SA-4.0**. Internal evaluation and threshold calibration are fine; it must **not** be embedded in, or required by, anything Versed ships commercially. MetricX-QE licensing to be checked at implementation.

Decisions:
- **D4c** ~~[HUMAN ratifies] Token-window handling for QE.~~ **SETTLED AND IMPLEMENTED 2026-08-14 via D2e (EXP-20260814-06).** Blocks were taken, and they dissolve it: **`truncated_fraction` 0.3754 → 0.0073** on the same 139 items, with median QE input 1,085 → 394 tokens. The residual 47 truncated segments come from exactly 3 of 522 blocks that ran to the generation cap in a repetition loop; those are now reported as `max_new_tokens_truncated` errors, which takes the figure to **0.0000**. Neither chunk-and-aggregate nor a longer-context QE model was needed. The measurement reproduces the published 0.3754 baseline exactly through the same `metricx_encode` code path before being applied to blocks, so the two numbers are comparable.
- **D4** [HUMAN ratifies] Do existing QE systems suffice as the core signal? → **Evidence says NO as a primary gate.** Recommendation: ensemble COMETKiwi (fluency) + deterministic fidelity checks; defer any custom neural QE until the ensemble is measured against human judgments.
- **D4b** [AGENT designs, HUMAN ratifies] Versed-QE must run in two modes: a **research** mode (may use NC models like COMETKiwi) and a **shippable** mode (deterministic checks + permissively-licensed signals only). **Materially advanced 2026-08-14:** MetricX-24 is apache-2.0, so the shippable mode now has a real neural signal rather than deterministic checks alone. The case for training our own QE model is correspondingly *weaker* — but not closed, because MetricX misses the same three critical fidelity errors COMETKiwi does.

**TRUNCATION CONFOUND RETIRED (2026-08-14 — EXP-20260814-06).** The 37.5% figure above was the single largest threat to this matrix's validity, and it is gone: translating in blocks takes `truncated_fraction` to **0.0073** (0.0000 excluding three degenerate generations), with median QE input 1,085 → 394 tokens. Every row that was biased low because the *corrupted* side truncated more than the clean side — `duplicate_sentence` and `hallucinate_prose` above all — can now be measured honestly. **The published `duplicate_sentence` 0.065 / −1.36 mean delta should be treated as retracted pending the block-level rerun**, since it was diagnosed as an artifact of the cap.
**Block-level matrix IN FLIGHT (launched 2026-08-14 20:41, ETA 7.4–9.2h):** 3,235 pairs / 6,470 segments over the 522-block TG12B run (`~/versed-translator-data/qe/tg12b-blocks-metricx/`; log `metricx-blocks.log`, sentinel `done-metricx-blocks` — absent = running, `0` = success). 14/15 injectors now exercised (`collapse_paragraphs` fires on block output where it could not before; only `alter_citation` remains unexercised on this slice). **Verify `score_min`/`score_max`/`distinct_scores` before trusting any rate** — and note the denominator changed (6,470 vs 2,288 segments, shorter each), so compare *per-injector rates*, never raw counts.

⚠️ **MetricX CPU cost scales sub-linearly with input length, so blocks cost ~2× more in total.** Direction is solid; the magnitude is a **range**, and is deliberately quoted as one. In-flight marginal rates between progress samples were **4.1–5.1 s/segment** on 394-token block inputs against the item-level study's completed **7.24 s/segment** on 1,085-token inputs — so a 2.83× shorter input buys only **29–43%** less time per segment (fixed per-segment overhead dominates), while blocking multiplies segment *count* by 2.83×. Net **1.6–2.0×**: **7.4–9.2h** against 4.6h.

**Why a range, and a methodology note worth keeping:** three successive estimates in one session read 5.5, 4.2 and 5.4 s/segment, and each looked authoritative. Two causes. (1) *Gross* rate (wall ÷ segments) includes the one-off model load, so it drifts downward as the run proceeds — 5.65 → 5.38 → 4.97 across samples — and is not a stable estimator early on; use the marginal rate between samples. (2) The sampling machine was concurrently running this session's test suite and tokenizer work, so all in-flight figures are **upper bounds on a quiet machine**. **The exact number is `scoring_seconds` in the finished summary — take it from there and replace this paragraph, rather than re-deriving from a partial log.**

**Blocks make QE more accurate and roughly twice as expensive at the same time**, the opposite of the intuition the design was chosen on. Any QE run over a genre-diverse (larger) benchmark must therefore go to Modal; the standing rule now has a number behind it.

**STATUS:** ACTIVE — COMETKiwi detection matrix DONE (30.4%, verdict above; **no further COMETKiwi investment — its role is settled: research-mode fluency signal, NC-licensed, threshold tuning on it is sunk cost**). MetricX full item-level matrix DONE (30.7%). Block-level MetricX matrix in flight per above.
**NEXT DEPENDENCY:** none for the block-level matrix (existing outputs suffice); diverse benchmark (D1e) for a matrix worth re-freezing.

---

## C5 — Versed-QE v0 (router)

**END STATE:** Installable `versed_qe` package: `(arabic, english, metadata) → {ACCEPT | REPAIR | HUMAN_REVIEW}` + calibrated `p_substantive_error` + `reasons[]`. Features: QE ensemble + deterministic checks (length ratio, entity/number/date coverage, Qur'anic-quotation match, isnad preservation, untranslated Arabic, repetition, terminology consistency — seeded from the `local_translation` fidelity rules). Interpretable model (logistic/GBT) calibrated on held-out judgments; reliability diagram published; precision/recall measured at three named threshold profiles (conservative/balanced/aggressive). No neural QE training unless D4 showed material gaps.
**Verify:** `uv run pytest qe/` green including a calibration bound test; report with reliability diagram; import-contract test proving the versed VPS worker can call it.

Checkpoints:
1. [AGENT] ~~Deterministic checkers + unit tests~~ **done 2026-08-14** (9 checks, 25 tests; one known gap documented above).
2. [HUMAN] Human judgment set for calibration: ~300–500 passages labeled (Bilal + optional recruited reviewer; the label = "would a competent bilingual editor find a substantive error?").
3. [AGENT] Train/calibrate/evaluate; freeze v0 thresholds.

Decision:
- **D5** [HUMAN] Threshold profile for the pilot (recommend **conservative**; compute is cheap, corpus-scale errors are not).

**STATUS:** ACTIVE — checkpoint 1 (deterministic checks) done 2026-08-14. Router design waits on the MetricX-QE result (C4) — its license determines the shippable-mode feature set — and calibration waits on checkpoint 2's human judgment set, **the longest serial [HUMAN] task on the critical path; start it early.**
**NEXT DEPENDENCY:** C4 MetricX result; checkpoint 2 labeling.

---

## C6 — Versed Parallel: rights inventory + provenance resolver

**END STATE:** A queryable works×translations inventory (parquet/SQLite in-repo, Supabase-syncable later) covering **the top ~200 priority OpenITI works** (seeded from versed's `openiti-rollout-priority` config): canonical identity, OpenITI URI, upstream digital source claim, existing English translations with translator/year/source/rights, `commercial_status ∈ {COMMERCIAL_SAFE, COMMONS_ONLY, RESTRICTED, UNKNOWN}`, alignment status. A provenance resolver that extracts the upstream-source claim from OpenITI URIs/metadata for ≥90% of the top-200. The OpenITI rights question sent and the answer (or non-answer) recorded.
**Verify:** `uv run versed-corpus stats` prints rights-bucket counts over ≥200 works; resolver coverage ≥90%; letter status recorded here.

Checkpoints:
1. [AGENT] ~~Inventory schema + ingest~~ **done 2026-08-12** — `corpus/inventory.sqlite` from the versed priority list (8,791 URIs); top-250 pass: **meta hit-rate 99.6%** (one URI genuinely lacks meta on the share). Source-library distribution (top 250): JK 126, Shamela 60, ShamAY 18, Shia 7, Zaydiyya 5, others ≤3, unresolved 12. PD-translation seed list: **16 works, 9 genres** (`corpus/pd_translations_seed.json`, verified URLs).
2. [AGENT] ~~Provenance resolver v0~~ **done 2026-08-12** — **96.5% top-200 coverage (≥90% target MET)**; the 7 unresolved are irregular tail formats (`Sham19Y…`, `…BK2-ara2`), documented for a v1 loosening if they matter.
3. [AGENT] Draft OpenITI letter → **[HUMAN] D6a approve + send.** Draft essence (from the planning conversation): *we strip OpenITI markup/metadata and use only underlying public-domain Arabic strings, most originating in pre-existing digital libraries; we create our own segmentation, translations, audio; is BY-NC-SA intended to cover those underlying strings or OpenITI's annotations/corpus-database; and would you grant Versed commercial permission for this public-access project?*
4. [HUMAN] **D6b** — French/EU IP counsel (1–3h) on the database-rights + AI-translation + phonogram questions. Required before **commercial** exploitation; not required for research/benchmarking. Schedule when C9 pilot approaches.

Standing constraint (**D6c**, enforced by [AGENT]): hadith-json/Sunnah.com material is used for matching/indexing only — its English never ships and never trains.

**STATUS:** ACTIVE — checkpoints 1–2 complete, both ≥90% targets met. Checkpoint 3 done: the OpenITI letter was **sent 2026-08-14**; Sarah Savant replied the same day, cc'd the Transform project team, and took it to their team meeting — awaiting their decision, and they asked to see our structural annotation.
A harvest pipeline landed with this component (`src/versed_translator/corpus/`: `catalogs`, `probe`, `fetch_pd`, `extract_train`, `join`, `translations`, `outreach`; artifacts in `corpus/`). **Scraping is retired as of 2026-08-19** — 24 logged passes produced 13 keepers total, 11 of them from a single archive.org bulk query, and the last 16 passes produced **zero** across ~180 candidates. Do not restart the harvest loop expecting books; the al-islam person-page seam is mined out.
**NEXT:** growth now comes from `corpus/rights_outreach.json` (58 entries, 5 hosts, 57 `not_started`) — asking rights holders for CC-BY/CC-BY-SA. That file holds no email addresses, only web forms and permissions pages, so every ask needs a contact looked up first.
**NEXT DEPENDENCY:** D6a approval to send the letter.

---

## C7 — Versed Align (engine)

**END STATE:** Installable `versed_align`: `(arabic_segments[], english_text) → alignment links {1:1, 1:N, N:1}` with per-link confidence, via the staged process (normalize → structural anchors [headings, hadith numbers, names, dates, Qur'an refs] → multilingual embeddings → monotonic DP → LLM only for ambiguous windows → confidence). Validated on ≥3 gold works of different shapes (a hadith collection via LK, a Wikisource history, the Ormsby Ihya section): **≥95% link agreement** against ≥200 human-checked links per work. A full book aligns in bounded time on one machine. Alignments stored separately from segmentation (mirrors versed's model).
**Verify:** `uv run pytest align/` green; validation report with agreement ≥95% ×3 works; HTML side-by-side demo artifact renders.

Decision:
- **D7** [AGENT recommends] Embedding model + LLM-window budget per book (cost/agreement tradeoff, measured).

**STATUS:** ACTIVE — engine built and installable, merged to main 2026-08-19. `versed-align` entrypoint over `src/versed_translator/align/` (16 modules, 3,707 lines: normalize → structural anchors → embeddings → monotonic DP → bundles → reader bridge); tests green; documented in `docs/ALIGNMENT_BUNDLES.md`, `docs/ALIGNMENT_ALGORITHM_REVIEW.md`, `docs/READER_ALIGNMENT_BRIDGE.md`.
**END STATE NOT MET.** Structural alignment is confirmed on **one** work (Hamadhani: 51 Arabic units ↔ 51 English units, 51/51 bilateral). Sentence-level accuracy is **unvalidated** — no independent gold links exist, so the scorer returns `unscored` and the review publishes no agreement percentage ("accuracy evidence: insufficient"). The ≥95% × 3 works bar is therefore unmeasured, not missed.
**NEXT:** freeze independent sentence gold for one work before any further parameter tuning, then widen to three works of different shapes.
**NEXT DEPENDENCY:** C0; benefits from C6 inventory. Unblocks benchmark v0.2 + C8 corpus scale.

---

## C8 — Training corpus + Versed Translate 27B v0.1

**END STATE (corpus):** 100k–250k pairs; per-pair provenance (work, genre, date, translator, rights, alignment confidence, human/synthetic flag); minhash-deduplicated; genre-stratified (30–50 well-chosen books over hundreds of repetitive ones); **contamination CI gate green against the frozen benchmark including its private split**.
**END STATE (model):** LoRA/QLoRA fine-tune of the C2-chosen base (default assumption: TranslateGemma 27B); controlled experiment series (LR, rank, epochs, length/genre mix, human-only vs +synthetic) logged in `TRANSLATION_EXPERIMENTS.md`; every checkpoint evaluated on the frozen benchmark; **v0.1 beats base on aggregate AND on ≥7/10 genre slices with no genre regressing >1%**; adapter + recipe reproducible; model card drafted with honest limitations.
**Verify:** contamination gate in CI; eval table base-vs-v0.1 by genre and error category; reproducibility hash of the winning run.

Decisions:
- **D8a** [HUMAN, evidence from AGENT] **GO/NO-GO gate:** if fine-tuning does not materially improve the benchmark — stop and diagnose, do not scale.
- **D8b** [AGENT runs, HUMAN ratifies] Data-mix experiment outcome (human-only vs human+synthetic distillation).
- **D8c** [HUMAN] Fine-tune compute cap (placeholder $200–600 across the series).
- **D8d** evidence-gated: terminology/glossary conditioning (Phase 12; seed = `alignment/glossary.json`) only if v0.1 shows measurable terminology inconsistency.

**STATUS:** NOT STARTED.
**NEXT DEPENDENCY:** C1 (frozen), C7 (pairs at scale), C2 (base choice).

---

## C9 — Cascade simulation, repair loop, pilot book

**END STATE (cascade):** simulation over benchmark outputs reporting, per threshold profile: expected substantive-error rate, % auto-accepted, % repaired, % human review, compute cost, whole-corpus projection — the cost-quality frontier, written down.
**END STATE (repair):** implemented loop `translate → QE → REPAIR → repair-model → QE → accept/human`, max 2 rounds, never infinite; measured evidence of which repair strategy actually improves QE + reference measures.
**END STATE (pilot):** ONE substantial book (100k–500k words) through the **full factory path** unattended: ingest → segment → provenance → existing-translation check → translate → QE → repair → editions stored → reader renders with labels; ~100 random + targeted-edge-case human audit meets the D9b bar; complete failure log (malformed source, poetry, truncation, crashes, resume behavior, cost actuals).
**Verify:** frontier report exists; repair A/B numbers recorded; pilot book readable on versed.page with translation labels; audit sheet ≥ bar; `books`-level cost ledger row matches prediction ±30%.

Decisions:
- **D9a** [HUMAN] Pilot book selection. Recommendation: an **Ihya quarter** (Ormsby anchors give a gold audit reference, already partially ingested) or **Musnad** (already migrating; hadith structure stress-tests isnad handling).
- **D9b** [HUMAN] Pilot acceptance bar (suggested: ≥97% of audited samples free of substantive error at the conservative threshold).

**STATUS:** ACTIVE — partial. The cascade half exists, merged to main 2026-08-19. `src/versed_translator/factory/` (1,380 lines: `router.py`, `glossary.py`, `consensus.py`, `merge.py`, `prepare.py`, `simulate.py`) runs a policy simulation over the 50-item set and reports the decomposition: escaped blockers 4/50, human queue 14/50, verse/sajʿ → Flash 14/50, additional Flash escalations 10/50. **A 28% human queue is not yet a scalable factory** — read the decomposition, never "keep-both 46/50" as an autonomous publication rate.
**Repair loop: NOT IMPLEMENTED.** **Pilot book: NOT STARTED.** The frontier report is not yet written; Blind-50 is the trigger for the book (see `STATUS.md` → Next 3 things).
**NEXT DEPENDENCY:** C5, C8 (or C2 baseline model if C8 is delayed — the pilot can run on the best base model to de-risk the factory earlier).

---

## C10 — Factory integration (lives in the `versed` repo)

**END STATE:** Translation derivatives flow through versed per its contract: explicit producer creates edition/queue rows → VPS worker consumes → calls the Modal model adapter → stores translations + QE scores/routing status (thin idempotent migration extending `block_translations`/edition rows — no new competing tables) → cost-ledger rows → `/openiti-ops` shows translation progress alongside audio. Idempotency keys prevent duplicate work; kill-worker-mid-book resume test passes with zero duplicates.
**Verify:** contract tests in versed; one work end-to-end via the real queue; chaos-resume test green; dashboard panel live.

Decision:
- **D10** [HUMAN reviews] The schema migration draft (Phase-0 residuals in `VERSED_TRANSLATION_ARCHITECTURE.md` §9 must be resolved first).

**STATUS:** NOT STARTED.
**NEXT DEPENDENCY:** C9 pilot design (they land together; pilot runs *through* this integration).

---

## C11 — Audio + reader deltas

Arabic audio is production-proven (Fish coordinator, Risala 779/779). Deltas only:
**END STATE:** pilot book has synchronized Arabic + **English** audio with provenance labels; reader shows the four human-readable translation-status labels with deep provenance on demand (never raw QE scores as truth); translation-version bump invalidates dependent audio automatically; English TTS provider/voice rights recorded per the master-plan audio fields.
**Verify:** pilot book plays bilingually on versed.page; label + provenance panel render; version-bump → audio invalidation test passes.

Decision:
- **D11** [HUMAN] English TTS provider/voice + written rights record (taste + rights; Cut 8 already requires written voice permission for public Wuquf distribution).

**STATUS:** NOT STARTED.
**NEXT DEPENDENCY:** C9 pilot translations accepted.

---

## C12 — Releases, flywheel, sustainability

**END STATE v1:** where rights permit — model adapter + card, benchmark public split (with canaries), `versed_qe`, `versed_align`, rights-safe parallel data, each with its **own** license file (no blanket license); public dashboard fields on wuquf (works, words, audio hours, QE acceptance, model version, funding, books seeking sponsors); correction path spec'd (reader report → editorial verification → gold correction dataset → future training, never auto-training on anonymous edits); OpenITI answer + counsel answers recorded before anything commercial ships.
**Verify:** release checklist per artifact; dashboard live; correction-path spec merged.

Decisions: **D12a** [HUMAN] release timing/naming (HF org). **D12b** [HUMAN, AGENT drafts] per-artifact licenses (suggested: code Apache-2.0; adapter under Gemma-terms-compatible terms; benchmark public split CC BY + canaries; data per-source). **D12c** [HUMAN] sustainability experiments (fund-a-book pricing already live at ~$20 on wuquf).

**STATUS:** NOT STARTED.
**NEXT DEPENDENCY:** C8/C9 outcomes.

---

# Sequencing

```
        C0 ──► C1 ──► C2 ──► C4 ──► C5 ──┐
        │       ▲      │                  ├──► C9+C10 ──► C11 ──► C12 ──► scale (Phase 24)
        │       │      └──► C3 (econ) ────┤
        ├──► C6 ┴──► C7 ──► C8 ───────────┘
        └──► (letter D6a out early — answer arrives while we build)
```

- **Critical path:** C1 → C2 → C4 → C5 → C9/C10.
- **Parallel from day one:** C6 inventory + D6a letter; C7 alignment; C2 harness skeleton while C1 assembles.
- **De-risk option:** C9's pilot may run on the best *base* model before C8 finishes — factory plumbing and model quality are independent risks; don't serialize them.
- Nothing blocks on counsel (D6b) except commercial exploitation.

# Budget picture (placeholders until C3 — every spend gated by a [HUMAN] cap)

| Item | Placeholder est. | Replaced by |
| --- | --- | --- |
| Bakeoff (API + GPU) | $150–400 | C2 actuals |
| Throughput grid | $100–300 | C3 actuals |
| QE eval GPU | ~$50 | C4 actuals |
| Fine-tune series | $200–600 | C8 actuals |
| Pilot book | $20–100 | C9 actuals |
| Whole-corpus first pass | $650–3,000 (API route, conversation est.) | C3 model × C13 frontier |

# Decision queue (what needs Bilal, roughly in order of arrival)

| ID | Decision | When |
| --- | --- | --- |
| D0 | ~~Repo visibility~~ **DECIDED: public** | done 2026-08-12 |
| D1c | Benchmark publication policy (public split + private held-out) | with C1 freeze |
| D1d | ~~ATHAR license conflict~~ **DECIDED 2026-08-14: MIT / commercially usable** (issue #4). Carve-out: filter modern editorial matter (مقدمة المحقق) — MIT can't grant copyright the creator doesn't own. | done |
| D1e | ~~Genre-coverage fork~~ **DECIDED 2026-08-14: option (d)** — targeted passage alignment from the PD translations, benchmark-scale only (issue #1) | done |
| D2c | ~~Provider keys or descope~~ **DECIDED 2026-08-14: keys** (issue #3). DeepSeek + Qwen live and verified; Gemini/OpenAI still descoped. | done |
| D2e | ~~Ratify structured block translation as production contract~~ **DECIDED + IMPLEMENTED 2026-08-14** (EXP-20260814-06): harness default, ID loss is a run metric, truncation 0.3754 → 0.0073. Answers **D4c** too. | done |
| D2b, D3b | Spend caps: bakeoff, throughput grid | C2/C3 start |
| D2a | Ratify baseline translator (largely forced → TG27B; see C2) | after TG12B leg |
| D6a | ~~Approve + send OpenITI letter~~ **DECIDED + SENT 2026-08-14** (issue #5). Reply received same day; OpenITI's Transform team is deciding, and asked to see our structural annotation | done — awaiting their answer |
| D5 | Threshold profile (recommend conservative) | C5 done |
| D8a/c | Fine-tune GO/NO-GO + compute cap | C8 |
| D9a/b | Pilot book + acceptance bar | C9 start |
| D11 | English voice + rights record | C11 |
| D6b | Counsel engagement | before commercial |
| D12a/b/c | Releases, licenses, sustainability | C12 |

# STATUS ledger

| Component | Status |
| --- | --- |
| C0 lab repo | COMPLETE |
| C1 benchmark | ACTIVE |
| C2 harness/bakeoff | ACTIVE |
| C3 economics | NOT STARTED (the local ~2 tok/s TG12B number is a dead-end datum from an abandoned path, not a C3 measurement; defer until model choice is real) |
| C4 QE truth study | ACTIVE (COMETKiwi matrix done: 30.4% detection, critical blind spots) |
| C5 Versed-QE v0 | ACTIVE (9 deterministic checks done; router next) |
| C6 rights inventory | ACTIVE (OpenITI letter sent 2026-08-14; scraping retired 2026-08-19 — outreach is the growth path now) |
| C7 Versed Align | ACTIVE (engine built + installable 2026-08-19; structural confirmed on Hamadhani only, sentence-level gold not yet frozen — END STATE unmeasured) |
| C8 corpus + 27B | NOT STARTED |
| C9 cascade/pilot | ACTIVE — partial (cascade sim + policy decomposition on 50 landed; repair loop and pilot book still to build) |
| C10 factory integration | NOT STARTED |
| C11 audio/reader deltas | NOT STARTED |
| C12 releases/flywheel | NOT STARTED |
