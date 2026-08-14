# VERSED_TRANSLATION_ROADMAP.md

**Living document.** Master destination: `VERSED_TRANSLATE_MASTER_PLAN.md`. Current-state grounding: `VERSED_TRANSLATION_ARCHITECTURE.md`. Experiment ledger: `TRANSLATION_EXPERIMENTS.md`.
**Last updated:** 2026-08-14

---

# START HERE (fresh session orientation)

Read this block, then §Component end states for whatever you pick up. Everything below is measured, not planned — treat any number without a date as unverified.

**Bilal does not read this file.** Open decisions live as answerable cards at the top of the dashboard (**https://bilalghalib.github.io/versed_translator/**), backed by `decisions/decisions.json` and one GitHub issue each (label `decision`). Agents: run `gh issue list --label decision` at session start — an answered issue is an instruction. When one is answered, set `status`/`decided` in `decisions/decisions.json`, close the issue, and reflect the outcome here in the same commit. Never invent an answer for an open decision, and never route a new [HUMAN] decision through this doc alone — add a brief so it shows up where he'll see it.

**Where we actually are (2026-08-14).** Master-plan execution steps 0–7 are underway *in the prescribed order*. The machinery works end to end: benchmark assembly → harness → GPU serving → QE study. What is thin is **depth at each step**, not sequence.

**⚠️ The one thing to fix before trusting any result: the benchmark is 99.6% hadith** (1,107 of 1,111 draft_test items are LK Hadith; ATHAR contributes 4; zero tafsir, philosophy, adab, history, poetry). Every headline number below was measured on that single genre. Hadith is unusually formulaic (isnad chains, fixed openings), so **none of these results can be assumed to generalize.**

**⚠️ Correction (2026-08-14 drift review): genre diversification is NOT a sampling fix, and ATHAR cannot supply it as-is.** Two measured facts (recorded in `src/versed_translator/benchmark/assemble.py`): (1) ATHAR's parquet files carry only `(arabic, english)` columns — no per-row work/author/genre metadata exists, so genre stratification over ATHAR is impossible today; (2) ATHAR's median is 18 Arabic words, below the benchmark's own 30-word band floor — that, not a sampler bug, is why only 4 ATHAR rows survived. Genre coverage is therefore a **data-source decision** — see **D1e**, a [HUMAN] fork. Do not start an agent session on "fix genre coverage" before D1e is decided; it will stall or silently balloon into C7.

**Update 2026-08-14: D1e option (d) now has a working first slice — 39 aligned *history* passages from al-Baladhuri / Hitti**, the first non-hadith genre in the benchmark. Method, yield and honest limits in C1 below; a [HUMAN] spot-check page is built and waiting at `~/versed-translator-data/benchmark-alignment/baladhuri_hitti/review.html` (off-repo: it contains corpus text). The measured yield says one work gives ~30 passages in the 100–250 band but only ~9 in 250–600, so **closing the long-band gap needs 3–4 PD works, not one.**

**Measured results so far** (all hadith-only, see caveat above):
- **C2 bakeoff:** TG27B, TG12B and Claude Sonnet 5 all 139/139 clean — chrF **50.24 / 49.86 / 50.60**. TG27B ran ~36× faster than Claude (0.68s vs 24.5s mean) at ~$0.27; **TG12B reaches 99.24% of 27B's chrF for 2.14× less GPU time at $0.20**, making it the serving-economics favourite. ⚠️ TranslateGemma ran on a *weaker prompt* than Claude (mislabel, see C2) — its near-parity understates it. Qwen-MT / Gemini / DeepSeek never ran (no API keys) → **D2c**.
- **C4 QE study:** COMETKiwi detects **30.4%** of 1,144 injected errors. Negation deletion 10.9%, terminology 0.8%, agent/patient reversal 9.1%. Clause removal has a **negative** mean delta — it scores truncated text *higher* than complete text. Only fluency artifacts are caught well (duplicate sentence 71.9%). **COMETKiwi is a fluency signal, not a safety gate.** MetricX-QE still untested, so this rests on one model.
- **C5:** 9 deterministic checks built against those measured blind spots. One documented gap: partial clause removal is undetectable from (source, output) alone on unpunctuated classical Arabic — likely fixed by structured block translation with ID preservation (the harness already supports it), not by threshold tuning.

**Recommended next actions (updated 2026-08-14 after drift review):**
1. **[HUMAN] one sitting (~45 min), before more agent work — the loops below all trace to pending human decisions being worked around instead of made:**
   - Send the OpenITI letter (D6a — drafted since 2026-08-12).
   - Email the ATHAR author — **one email, two questions**: which license is intended (D1d), and does per-row work/genre provenance exist for the pairs (feeds D1e)?
   - Decide D2c: provision Gemini/Qwen/DeepSeek keys, or formally descope the bakeoff field (see C2 — D2a is largely forced anyway).
   - Ratify D2e: structured block translation with ID preservation as the production contract (dissolves C5's worst known gap architecturally — cheaper than any detection scheme).
2. **[AGENT] meanwhile, on existing artifacts (no new benchmark needed):** MetricX-QE over the existing TG27B outputs — check its license first; if permissive it is the **only** shippable neural QE candidate (COMETKiwi is NC), which changes C5's feature set, so this must land **before** router design. Then the TG12B Modal leg — the 12B↔27B gap is unmeasured and drives all serving economics.
3. **After D1e is decided:** rebuild the benchmark **once**, freeze it, run the full measurement suite **once** (bakeoff legs + QE matrix + deterministic checks). **No re-measurement treadmill:** settle all inputs (benchmark composition, keys yes/no, MetricX in) before spending GPU money on a re-run.
4. C5 router only after MetricX results + the start of the human judgment set (C5 checkpoint 2 — the longest serial [HUMAN] task on the critical path; start labeling early).

**Traps already paid for — do not re-derive:**
- A full row count, clean exit code, and populated output file are **all compatible with total failure**. A 139-row run was 139 connection errors; the tell was `wall_s: 0.06`. Always check the error field *and* a plausibility signal.
- `nohup … & disown` does **not** survive session teardown. Use `subprocess.Popen(..., start_new_session=True)` locally and `modal run --detach` for Modal; write a `done-<job>` sentinel with the exit code.
- vLLM 0.11.0 declares `transformers>=4.55.2` unbounded → pip takes v5, which renamed `rope_scaling`→`rope_parameters`. Pin `transformers<5`. Patching the model's `config.json` does **not** help (three attempts proved it).
- Sonnet 5 runs adaptive thinking by default and `max_tokens` caps thinking **plus** text; too small a budget returns empty translations with `stop_reason: max_tokens`.
- Local CPU inference for 12B is ~2 tok/s — unusable. Use Modal.
- `setsid` does not exist on macOS — a launch wrapped in it silently no-ops. Use `subprocess.Popen(..., start_new_session=True)`.
- **A metadata label is not evidence.** Both Modal legs recorded `prompt_template_id: "v1"` while sending a different prompt entirely; nothing failed, and the bakeoff's headline comparison was quietly confounded for a day. When a run records *what it did*, verify the field against the code path that actually ran.
- `/Volumes/hikma` (SMB) can degrade mid-session to permission-denied at the share root, breaking symlinks, filelock, curl, cp, rsync and dd in that order. Stage large downloads to the session scratchpad; prefer `ssh nautilus`, where the disk is local at `/mnt/hikma`.

**Open [HUMAN] items:** OpenITI letter (D6a, drafted at `OPENITI_LETTER_DRAFT.md`); genre coverage (D1e); structured blocks (D2e) + token window (D4c), which decide together; C5 threshold profile (D5). ~~ATHAR license (D1d)~~ and ~~provider keys (D2c)~~ resolved 2026-08-14.

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

**Arabic side VERIFIED 2026-08-14 (via `ssh nautilus`, where the disk is local at `/mnt/hikma`).** All nine candidate works exist in OpenITI with real text — every OpenITI URI *guessed* in `PD_TRANSLATIONS.md` resolved:

| OpenITI text | d. | genre (`021.BookSUBJ`) | `### |` sections |
| --- | ---: | --- | ---: |
| `0279Baladhuri.FutuhBuldan` | 279 | التاريخ (history) | 90 |
| `0681IbnKhallikan.WafayatAcyan` | 681 | التراجم والطبقات (biography) | 33 |
| `0516IbnCaliHariri.Maqamat` | 516 | عيون الشعر العربي (poetry/adab) | **0** |
| `0581IbnTufayl.HayyIbnYaqzan` | 581 | علوم أخرى (philosophy) | 3 |
| `0139IbnMuqaffac.KalilaWaDimna` | — | *(none)* | 30 |
| `0779IbnBattuta.Rihla` | 779 | البلدان والجغرافيا والرحلات (travel) | 527 |
| `0346Mascudi.MurujDhahab` | 346 | كتب متنوعة (misc/history) | 1750 |
| `0486IbnAhmadZuzani.SharhMucallaqat` | 486 | الأدب والبلاغة (adab/rhetoric) | 653 |
| `0505Ghazali.KimiyaSacada` | 505 | الرقاق والآداب (devotional/ethics) | 24 |

**Two findings that change C1's shape:**
1. **OpenITI metadata carries per-work genre (`021.BookSUBJ`) and death date (`011.AuthorDIED`) — the exact metadata ATHAR lacks.** Genre labels and century banding come free from the source, with no inference and no author email. The nine works above span **9 distinct centuries** (139–779 AH), which alone satisfies the "≥5 centuries" coverage minimum.
2. **Section structure is per-work, not uniform — segmentation is a per-work task, not one parser.** Hariri's *Maqamat* has **zero** `### |` markers despite being the most naturally segmented work in the list (50 discrete maqamat), so its anchors must come from in-text maqama numbering. Ibn Khallikan shows only 33 sections across 6.2MB, so those are volume divisions, not the per-biography entries that make it attractive as an alignment target. Mas'udi's 1,750 sections are finer than passage-sized. Budget per-work anchor logic.

**English side VERIFIED 2026-08-14** (all 16 PD URLs fetched; see the verification block at the top of `corpus/PD_TRANSLATIONS.md`, which is authoritative over that doc's original table). The compilation pass had never fetched a single URL, and it showed:

- **Two entries are NOT public domain and are dropped.** #13 *Mishkat al-Masabih* is not Matthews' 1809 text but Durrani's revised edition — "(All Rights Reserved)", modernist editorial matter woven into the body, and a part-issue fragment. #14 Rehatsek's *Sira* is the **1964 Folio Society Edwardes abridgement** (URAA risk, glosses inseparable from the prose). **There is no public-domain English Sira translation in existence** — Rehatsek's was the first and was not printed until 1964. Both would have put copyrighted text into a benchmark intended for public release; this is exactly the failure the rights-from-birth rule exists to prevent.
- **Six entries pointed at the wrong edition**, including two traps the doc had itself warned about: #8 Ibn Tufayl linked the 1929 Fulton revision the doc's own note said to avoid (the clean 1708 Ockley is on **Gutenberg**, human-proofread, zero OCR noise), and #15's secondary Qur'an URL was *Sacred Laws of the Aryas* — a different book. #1 Baladhuri returned **HTTP 401** (access-restricted 1968 reprint); #7 Hariri was vol II only, and a complete notes-free all-50 stream was found instead.
- **Ranked for alignment:** Hariri *Assemblies* (all 50, discrete units, no apparatus) → Ibn Khallikan (per-entry gold standard, cleanest long text) → Ockley's *Hayy* (flawless clean control) → Baladhuri → Blunt's odes → Knatchbull → Palmer → Hamilton.
- ⚠️ **The list contains zero tafsir.** Option (d) **cannot** close the tafsir hole; that genre needs its own sourcing decision.

**Format notes** (`######OpenITI#` mARkdown): `#META# key :: value` header block terminated by `#META#Header#End#`; `### |` section headings; `PageV##P###` page markers (444 in Baladhuri). The factory has a fuller parser at `versed_core/ingestion/openiti_ingest.py`, but it is coupled to Supabase and writes the v2 graph — the lab needs read-only passage extraction, so a light local reader is the right call rather than importing the factory's stack.

⚠️ **Access:** read OpenITI via `ssh nautilus` (`/mnt/hikma/OpenITI`), **not** the local SMB mount. `/Volumes/hikma/OpenITI/meta` listed 8,738 files and then returned "No such file or directory" seconds later in the same session — the documented SMB degradation. `books/` is genuinely empty on both; the content is in `texts/` (8,748) and `meta/` (8,738).
3. [HUMAN] ~100-item spot audit for alignment/reference quality (Bilal or recruited bilingual reviewer).
4. [AGENT] Freeze: tag, manifest, stats report, held-out split sealed.

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
**NEXT DEPENDENCY:** [HUMAN] review of `~/versed-translator-data/benchmark-alignment/baladhuri_hitti/review.html`, then the next 2–3 PD works (Ibn Khallikan's per-entry structure is the natural second; it should need only new per-work anchor logic, since the reader, transliteration and adjudicator are work-agnostic).

---

## C2 — Translation harness + bakeoff

**END STATE:** `versed-harness run --model <id> --benchmark v0.1` emits standardized JSONL (master-plan run schema: model, version, quantization, prompt template id, tokens, latency, cost, translation) for **every** candidate: TranslateGemma 27B, TranslateGemma 12B, Qwen-MT, Gemini Flash tier, DeepSeek V4, one frontier ceiling, plus the current-versed Claude few-shot-Ormsby configuration as continuity baseline. ID-preserving structured block output (`[{"id":"AR_001","english":...}]`) is tested, and ID-loss counts as an error metric. A comparison report by genre × length × error category exists, and the baseline-translator DECISION is recorded.
**Verify:** all candidate rows present in `harness/reports/bakeoff-v1.md`; every run JSONL validates; D2a filled in.

**MEASURED SO FAR (2026-08-13/14, dev_bakeoff 139 items):**

| Leg | Result |
| --- | --- |
| **Claude Sonnet 5** (ceiling) | ✅ **139/139 clean.** Mean latency 24.5s, p95 73.4s. ID preservation 100%. 3 items (2.2%) flagged for untranslated Arabic — the model appending scholarly commentary that quotes the Arabic back, not a fidelity failure. |
| **TranslateGemma 12B** (local Ollama) | ❌ Abandoned as a local leg. Measured **~2 output tok/s** on this Mac (100s wall for a 149-token short-band item; 74s pure generation) → full run is multi-hour and the machine thrashes. Moved to Modal GPU. |
| **TranslateGemma 27B** (Modal H100) | ✅ **139/139 clean.** chrF **50.24**. Mean latency 0.68s, wall 249s, **$0.2732**. |
| **TranslateGemma 12B** (Modal H100) | ✅ **139/139 clean.** chrF **49.857** — 99.24% of 27B's score (gap 0.38, 0.76% relative) for **2.14× less GPU time** and **$0.1989**. Mean latency 0.317s. **Zero** rows containing untranslated Arabic (27B had 2, Claude 3). |

⚠️ **PROMPT MISLABEL (found 2026-08-14, corrected).** Both Modal legs recorded `prompt_template_id: "v1"`; **that label is wrong.** `serve_translategemma.run_batch` hardcodes a three-sentence instruction and never touches `harness/prompts.py`. Harness `v1` carries the six fidelity rules — including *"Translate every clause. Do not summarize, compress, or silently drop material"*, the rule aimed at the omission failure C5 cannot detect. So **TranslateGemma-vs-Claude is a prompt comparison as much as a model comparison, and TranslateGemma ran on the weaker prompt** — its near-parity understates it, which strengthens D2a rather than weakening it. The 27B-vs-12B comparison is unaffected (identical template both sides). Fixed so it cannot recur: registered as `modal_minimal_v1`, `ingest-modal` requires an explicit `--template`, and `tests/test_prompts_modal_parity.py` pins the literal to the registry. **A matched-prompt bakeoff has never been run — fold it into the single post-D1e measurement suite, don't spend a separate run.**

**Reproducibility gap closed (2026-08-14):** the 27B leg's raw→harness-schema conversion had been done by an ad-hoc script that was not in the repo. Now `versed-harness ingest-modal`, validated by re-deriving the 27B run and diffing against the known-good output: `run_meta.json` matches on every field, `results.jsonl` on 13 of 14 — the exception being `output_tokens`, which the lost script wrote as `null` and the tool now carries through from the raw data (a strict superset, pinned by a regression test). Fields it cannot honestly derive stay null with documented reasons (`source_tokens`, `batch_size`, per-row `cost_estimate`).

**Bugs found and fixed while getting here** (all committed; each was a false-success or silent-failure class the factory phase must not inherit):
1. **Sonnet 5 token-budget trap** — adaptive thinking is ON by default and shares `max_tokens` with response text; at 4096 the longest passages spent the whole budget thinking and returned empty text (23/139). Default raised to 16k; `stop_reason == "max_tokens"` now reported as a named error, never an empty string.
2. **Runner lost whole runs** — one invalid row raised and discarded all 139 buffered results. Now demotes to an error row and writes incrementally.
3. **Cost never recorded** — adapters computed `cost_estimate` but the runner hardcoded `None`. Threaded end-to-end.
4. **chrF always null** — the score CLI never loaded `reference_english`, so reference-based scoring silently reported "no references". Now loaded from `run_meta.items_path`.
5. **Ollama adapter timeout** — 180s default vs. real ~2 tok/s produced an apparent 20-minute hang instead of a clean per-item timeout. Raised to 900s.
6. **vLLM `rope_scaling` crash (root cause)** — vllm 0.11.0 declares `transformers>=4.55.2` with **no upper bound**; pip installed transformers 5.x, which renamed `rope_scaling` → `rope_parameters`, so vLLM's `patch_rope_scaling()` saw a rope dict with no `rope_type` and raised. **Patching the model's `config.json` does not help** (the mismatch is in transformers' parsing, not the file) — three attempts proved that. Fix: pin `transformers<5` in the Modal image.

**Verification lesson (applies to every later phase):** a full row count, a clean exit code, and a populated output file are all compatible with total failure. A 139-row TG12B run was 139 connection errors; the tell was `wall_s: 0.06`. Always check the error field plus a plausibility signal (wall time, token counts), never row count alone.

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

**STATUS:** ACTIVE — harness + scoring built; dev_bakeoff (139 items, hadith-only) measured for Sonnet 5 and TG27B; TG12B Modal leg pending; full bakeoff blocked on D2c + C1 freeze.
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

**RESULT (2026-08-14, COMETKiwi over 1,144 corrupted pairs from the TG27B run, 13/15 error types exercised):**

**Overall detection rate 30.4% at delta>=0.02.** The failures cluster precisely on the highest-severity fidelity errors:

| Corruption | Severity | n | mean delta | detection |
| --- | --- | ---: | ---: | ---: |
| mistranslate_term | major | 120 | 0.0003 | **0.8%** |
| reverse_agent_patient | critical | 11 | 0.0063 | **9.1%** |
| delete_negation | critical | 92 | 0.0076 | **10.9%** |
| remove_isnad_narrator | critical | 127 | 0.0103 | 22.8% |
| remove_clause | critical | 105 | **−0.0041** | 22.9% |
| omit_quotation | critical | 131 | 0.0090 | 27.5% |
| duplicate_sentence | moderate | 139 | 0.0612 | 71.9% |

Three findings that shape C5:
1. **Deleting a negation is invisible (10.9%, mean delta 0.008).** Inverting a claim — the single most consequential corruption for doctrinal text — barely moves the score.
2. **Removing a clause has a NEGATIVE mean delta (−0.0041):** COMETKiwi scores the *truncated* text slightly **higher** than the complete translation. A fluency-weighted metric rewards silent omission, which is exactly backwards for a corpus where omission is the classic failure.
3. **Detection tracks fluency, not fidelity.** The only well-detected corruption is `duplicate_sentence` (71.9%) — a fluency artifact. Every semantic corruption sits at or below ~30%.

**Conclusion: COMETKiwi cannot be the primary safety gate for this corpus.** It is a usable fluency/adequacy signal, nothing more. Note this does **not** yet justify training a neural QE model — every one of its blind spots is cheaply detectable with deterministic checks (negation-count parity, sentence-count/length ratio, entity + isnad coverage, quotation-span coverage, terminology-glossary match). That is the C5 ensemble, and it is also the NC-free path (D4b), since the blind spots live in the NC-licensed model.

Artifacts (outside repo, rights): `~/versed-translator-data/qe/tg27b-full/{detection_matrix.json,detection_matrix.md,scored_pairs.jsonl}`.
Caveats: single QE model (MetricX-QE still untested); hadith-dominated slice; `alter_citation` and `collapse_paragraphs` not exercised (this slice has no verse citations or paragraph breaks); `alter_date`/`change_number` had n=1 each, so their 0% is directional only.

**MetricX-24 RESULT (2026-08-14, smoke: 20 items / 324 segments; full 1,144-pair run in flight):**

- **License: `google/metricx-24-hybrid-large-v2p6` is apache-2.0 and ungated** (verified against the HF API). This is the D4b unblock — the **first reference-free QE model in this project that shipping code may require.** Caveat: `metricx24` has no PyPI release, so the one needed model class is vendored at `src/versed_translator/qe/metricx_model.py` under its Apache-2.0 notice with deviations documented.
- **MetricX shares COMETKiwi's critical blind spots exactly:** `delete_negation` **0.0**, `mistranslate_term` **0.0**, `reverse_agent_patient` **0.0**. It is better on omission/untranslated-Arabic/hallucination (`remove_clause` 0.53 vs 0.23, `omit_person` 0.65 vs 0.30).
- **Two independent neural QE systems failing on the same three highest-severity fidelity errors is much stronger evidence for the deterministic ensemble than one was.** C5's checks are load-bearing, not a stopgap.
- ⚠️ **39% of inputs hit MetricX's 1536-token cap** (126/324). Truncation ~doubles apparent error (median 17.51 vs 8.88) and eats the *end* of the input — the candidate being judged — so length-increasing injectors are biased toward zero delta. The `duplicate_sentence` row is an artifact of the cap, not a fact about MetricX. This hits the 250–600-word band hardest, i.e. exactly where omission matters most. Instrumented (`truncated_inputs`/`truncated_fraction` in the summary), not fixed → **D4c**.
- Polarity trap handled: MetricX emits error on [0,25] (**lower is better**); the scorer negates internally so the engine's higher-is-better contract holds, with a regression test asserting that un-negated scores would produce 0% detection.
- Full run: log `~/versed-translator-data/logs/metricx-full.log`, sentinel `~/versed-translator-data/logs/done-metricx-full` (absent = running, `0` = success). **Verify `score_min`/`score_max`/`distinct_scores`/`truncated_fraction` before trusting any rate.**
- Serving note: 6.2 s/segment on CPU ≈ 3.8h for 1,144 pairs. Acceptable once; **any QE run over a genre-diverse (larger) benchmark should go to Modal**, per the standing "inference happens on Modal" rule.

Decisions:
- **D4c** [HUMAN ratifies] **Token-window handling for QE.** Options: chunk long passages and aggregate; adopt structured block translation (**D2e**), which makes blocks naturally short and largely dissolves this; exclude truncated rows from the matrix; or adopt a longer-context QE model. Note this is the *second* independent problem that D2e would solve — see the C5 clause-removal gap.
- **D4** [HUMAN ratifies] Do existing QE systems suffice as the core signal? → **Evidence says NO as a primary gate.** Recommendation: ensemble COMETKiwi (fluency) + deterministic fidelity checks; defer any custom neural QE until the ensemble is measured against human judgments.
- **D4b** [AGENT designs, HUMAN ratifies] Versed-QE must run in two modes: a **research** mode (may use NC models like COMETKiwi) and a **shippable** mode (deterministic checks + permissively-licensed signals only). **Materially advanced 2026-08-14:** MetricX-24 is apache-2.0, so the shippable mode now has a real neural signal rather than deterministic checks alone. The case for training our own QE model is correspondingly *weaker* — but not closed, because MetricX misses the same three critical fidelity errors COMETKiwi does.

**STATUS:** ACTIVE — COMETKiwi detection matrix DONE (30.4%, verdict above; **no further COMETKiwi investment — its role is settled: research-mode fluency signal, NC-licensed, threshold tuning on it is sunk cost**). Next: MetricX-QE over the same TG27B outputs + license check — if permissive it is the only shippable neural QE candidate, so it must land **before** C5 router design.
**NEXT DEPENDENCY:** none for MetricX (existing outputs suffice); diverse benchmark (D1e) for a matrix worth re-freezing.

---

## C5 — Versed-QE v0 (router)

**END STATE:** Installable `versed_qe` package: `(arabic, english, metadata) → {ACCEPT | REPAIR | HUMAN_REVIEW}` + calibrated `p_substantive_error` + `reasons[]`. Features: QE ensemble + deterministic checks (length ratio, entity/number/date coverage, Qur'anic-quotation match, isnad preservation, untranslated Arabic, repetition, terminology consistency — seeded from the `local_translation` fidelity rules). Interpretable model (logistic/GBT) calibrated on held-out judgments; reliability diagram published; precision/recall measured at three named threshold profiles (conservative/balanced/aggressive). No neural QE training unless D4 showed material gaps.
**Verify:** `uv run pytest qe/` green including a calibration bound test; report with reliability diagram; import-contract test proving the versed VPS worker can call it.

**PROGRESS (2026-08-14):** `versed_translator.qe.checks` implements 9 deterministic checks, each targeting a measured COMETKiwi blind spot: `negation_parity` (Arabic particle vs English marker counts — covers the 10.9% blind spot), `number_coverage` (Arabic-Indic digits normalized), `length_ratio_flag`, `sentence_ratio_flag`, `untranslated_arabic`, `repetition_flag`, `quotation_coverage`, `entity_coverage` (diacritic-folded, so `Mughīrah` == `Mughirah`), `terminology_violations` (glossary-conditioned). 25 tests, including an integration test that feeds the C4 injectors' own output through the checks.

⚠️ **KNOWN GAP — partial clause removal is not deterministically detectable** from (source, output) alone when the Arabic source lacks sentence punctuation, which is common in classical texts: `sentence_ratio_flag` can't run (source parses as one sentence) and a truncated output can still land inside the normal Arabic→English expansion band. COMETKiwi also misses it (22.9%, negative mean delta), so **neither signal covers the single highest-severity omission failure.** Closing it needs one of: punctuation-bearing sources, an aligned reference, **structural block-level translation with ID preservation (the harness's structured template already supports this — likely the cheapest fix)**, or a targeted LLM verifier. Asserted in `tests/test_checks.py::test_known_gap_clause_removal_on_unpunctuated_source` so it cannot regress silently.

**Design rule enforced throughout:** a check that cannot run returns `applicable=False`, never a passing verdict — an unrun check reading as "clean" is how a safety gate silently stops being one.

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

**STATUS:** ACTIVE — checkpoints 1–2 complete, both ≥90% targets met; next: checkpoint 3 (OpenITI letter — draft ready for D6a) and inventory fill beyond top-250.
**NEXT DEPENDENCY:** D6a approval to send the letter.

---

## C7 — Versed Align (engine)

**END STATE:** Installable `versed_align`: `(arabic_segments[], english_text) → alignment links {1:1, 1:N, N:1}` with per-link confidence, via the staged process (normalize → structural anchors [headings, hadith numbers, names, dates, Qur'an refs] → multilingual embeddings → monotonic DP → LLM only for ambiguous windows → confidence). Validated on ≥3 gold works of different shapes (a hadith collection via LK, a Wikisource history, the Ormsby Ihya section): **≥95% link agreement** against ≥200 human-checked links per work. A full book aligns in bounded time on one machine. Alignments stored separately from segmentation (mirrors versed's model).
**Verify:** `uv run pytest align/` green; validation report with agreement ≥95% ×3 works; HTML side-by-side demo artifact renders.

Decision:
- **D7** [AGENT recommends] Embedding model + LLM-window budget per book (cost/agreement tradeoff, measured).

**STATUS:** NOT STARTED. (Seed material exists: `alignment/` workspace, usul.ai API, Ormsby photos.)
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

**STATUS:** NOT STARTED.
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
| D1e | Genre-coverage fork — **new option (d): targeted passage alignment from the 16 PD translations, benchmark-scale only** (now recommended over a/b/c) | **now** — gates benchmark rebuild |
| D2c | ~~Provider keys or descope~~ **DECIDED 2026-08-14: keys** (issue #3). DeepSeek + Qwen live and verified; Gemini/OpenAI still descoped. | done |
| D2e | Ratify structured block translation as production contract | **now** — dissolves C5 known gap |
| D2b, D3b | Spend caps: bakeoff, throughput grid | C2/C3 start |
| D2a | Ratify baseline translator (largely forced → TG27B; see C2) | after TG12B leg |
| D6a | Approve + send OpenITI letter | early, async |
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
| C6 rights inventory | ACTIVE |
| C7 Versed Align | NOT STARTED |
| C8 corpus + 27B | NOT STARTED |
| C9 cascade/pilot | NOT STARTED |
| C10 factory integration | NOT STARTED |
| C11 audio/reader deltas | NOT STARTED |
| C12 releases/flywheel | NOT STARTED |
