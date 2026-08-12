# VERSED_TRANSLATION_ARCHITECTURE.md

**Date:** 2026-08-12
**Status:** Phase 0 deliverable — current-state snapshot of the Versed system as it bears on translation.
**Sources inspected:** `versed/AGENTS.md`, `versed/versed-app/docs/agentic/CURRENT_PIPELINE_CONTRACT.md` (2026-07-29, authoritative), `ACTIVE_RUN.md` (2026-08-03 checkpoint), `alignment/RESEARCH.md` (2026-03-26), `versed_core/derivatives/*`, `infra/modal/*`, live versed.page/wuquf.
**Conflict order in the versed repo:** code > `docs/ARCHITECTURE.md` > `CURRENT_PIPELINE_CONTRACT.md` > `AGENTS.md` > handoffs > memory. This snapshot ranks below all of those — verify against code before acting on it.

---

## 1. The two properties

- **versed.page** — bilingual reading product (personal reader, schools, upload-your-own). Business.
- **versed.wuquf.org** — public library of classical Islamic texts (waqf). Fund-a-book (~$20/book), 6-tier archival (Supabase, GitHub, Internet Archive, Arweave, Hugging Face, Academic Torrents), SHA-256 content hashing, charter on Arweave.

Same engine, different governance. Translation work must keep this boundary legible (rights statuses differ per property).

## 2. Runtime ownership (from the pipeline contract — binding)

| Runtime | Owns | Must not own |
| --- | --- | --- |
| Vercel API | auth, uploads, job enqueue, public cached reads | heavy processing |
| Supabase | `processing_jobs`, run/artifact rows, canonical graphs, direct object URLs | duplicate business tables |
| VPS/self-host worker | polling/executing jobs; **the durable translation/morphology derivative consumer**; audio storage/serving | divergent schema |
| Modal | **GPU/model adapters only** (OCR, Chatterbox, heavy models) | a second production queue |
| Frontend | explicit page/audio state | hidden fallbacks |

Other binding rules relevant to us: no new job type/table/endpoint unless it replaces an old one; migrations via `supabase migration new`, idempotent; new generated audio never goes to Supabase Storage; fail loud.

## 3. Canonical units

```
books → blocks → block_spans → span_words          (v2 segment graph; reader/audio source of truth)
renders, page_audio, page_audio_word_timings        (audio; timings are the only playback truth)
span_word_arabic_analyses                           (CATT contextual diacritics + Qalsadi lexical candidates)
processing_jobs / processing_runs                   (durable queue + execution ledger)
block_translations                                  (helper rows written by enrichment.translator)
edition-scoped spans/words                          (materialized by audio.v2.translation_renderer)
```

Contract revision: `segment-graph-audio-v2.2026-07-29` in `versed_core/runtime_contract.py`. Deployed services expose it at `/health`; compare before processing.

## 4. The OpenITI path as it runs today

```
modal_openiti_catalog_worker / _download  →  catalog + acquisition
versed_core/ingestion/openiti_ingest.py   →  writes blocks→block_spans→span_words directly (no PDF round-trip)
modal_openiti_typesetter / _catt          →  typesetting; CATT contextual diacritization (rollout in PR #149)
Fish audio coordinator                    →  Ogg/Opus + JSON timings, 700-char ceiling (human-approved),
                                             batch leases, retry telemetry, Drive spool/archival receipts
Reader                                    →  windowed canonical ReaderPage JSON; useOpenITIReader.ts;
                                             word highlighting; morphology inspector (lexical_candidate)
```

Campaign ops (live): feeder + Hikma-pull timers, queue with 75k watermark, 6 workers, `/openiti-ops` dashboard, cost counters. Completed pilots: **Risala** Arabic audio 779/779 chunks with restore-verified archival; **Musnad** storage migration in flight; **Ihya** partially processed (page-level, CATT-reprocessed). OpenITI parser (in `versed-pdf`) is 100% mARkdown-spec-compliant: 23+ block types, entities, hadith units, poetry.

## 5. Translation subsystems that already exist (three generations)

1. **`versed_core/enrichment/translator.py` — BilingualTranslator** (Claude-based). Block-level with context window, sentence-level, word-level; back-translation QC via Levenshtein. Generic prompts; writes `block_translations`.
2. **`versed_core/derivatives/local_translation/`** — scan-first local workflow (Ollama): BOOK_SCAN (brief) → BLOCK_TRANSLATE (one block per call) → QA (fidelity check), deliberately separate calls; `PROMPT_VERSION = "bukhala-local-v1"` participates in the idempotency key; **fidelity rules distilled from observed model failures** (divine names, rasul≠nabi, no added honorifics, translate every clause, preserve numbers/quotes/hedging). These rules are a seed for both harness prompts and QE deterministic checks.
3. **`versed_core/derivatives/translation_policy.py`** — shared block eligibility (skip quran_verse/footnote/header blocks, citation-only paragraphs, post-verse glosses). Both producers must agree via this module.

`alignment/` (repo root) is a March-2026 research workspace: `model_bakeoff.py`, `mega_bakeoff.py`, `glossary.json` (terminology seed), Ihya/Isharat/Furq English mARkdown outputs, HTML comparison reports.

## 6. Prior findings that must not be re-derived from scratch

- **Register bakeoff (2026-03-26):** GPT-5.4 few-shot with one Ormsby exemplar reproduced the Islamic Texts Society register; zero-shot was functional but flat. One example is enough to shift register.
- **GLM-5:** good at Arabic (#2 SILMA) but infra-broken for paragraphs (unbounded reasoning, token inflation, 502s). Sentence-at-a-time works and yields philological analysis worth harvesting.
- **DeepSeek/Gemma failure modes** produced the fidelity rules above; merging analysis into the translation call makes models explain instead of translate.
- **Arabic sources:** usul.ai content API (no auth, ~15k texts, clean paginated JSON, aggregates turath/shamela/OpenITI); turath.io as backup; shamela.ws locked. OpenITI best for structural markup + identity.
- **ACTIVE_RUN Cut 5** (pending in versed): a 40–60-passage blind bakeoff (DeepSeek V4 Pro thinking on/off, V4 Flash, Gemini Pro, Sonnet). **Superseded by** the lab's benchmark+bakeoff (C1/C2 in the roadmap) — do not run two divergent bakeoffs; close Cut 5 by reference when C2 reports.
- **TranslateGemma** is already pulled locally (`translategemma:latest` appears in bakeoff tool usage).
- Existing parallel resources (from the planning conversation; verify rights at ingest): **LK Hadith Corpus** (~39k hadith pairs, six collections, isnad/matn split), **hadith-json** (~51k pairs, scraped from Sunnah.com — matching/indexing only until rights clarified), **ATHAR** (~66k Classical Arabic↔English pairs, 18 works, CC BY-NC 4.0 — internal eval fine, commercial redistribution no), Wikisource/OTF/RAS public-domain translations (Hitti's *Origins of the Islamic State*, de Slane's Ibn Khallikan, etc.), Ormsby's Ihya Book 36 (copyrighted; internal gold reference only).

## 7. Where the translation subsystem attaches (the Phase 0 gate answer)

1. **Segmentation:** reuse the v2 graph written by `openiti_ingest.py`. Translation units = `blocks` filtered through `translation_policy.is_skippable_for_translation`. Do not invent a second segmentation.
2. **Job flow:** translation editions/queue rows are created **explicitly by producers** (PDF/OpenITI/CLI) — never implicitly by the store stage — and consumed by the **VPS worker**. The lab's chosen model is served behind a **Modal adapter endpoint** (same pattern as Chatterbox: VPS calls Modal, Modal never owns the queue).
3. **Storage:** `block_translations` helper rows + edition-scoped spans/words via `translation_renderer`. QE scores/routing status attach alongside these rows (thin, idempotent migration; prefer extending existing tables per the no-new-tables rule).
4. **Reader:** edition labels per master-plan Phase 18 (`Human translation` / `Human-reviewed Versed translation` / `Machine translation` / `Machine translation, automatically verified`), deep provenance on demand.
5. **Audio:** English audio is explicitly a **later, separate derivative** (per Cut 8 item 5). Translation version bump must invalidate/regenerate dependent audio.

## 8. Credentials, compute, and storage available today

- Modal: two profiles configured (`bilalghalib`, `sourced-workspace`).
- `ANTHROPIC_API_KEY` in environment. Gemini/Qwen/DeepSeek/OpenAI keys: to be provisioned when C2 adapters land.
- GitHub CLI authed as `bilalghalib`.
- Supabase target project (ref in local env; RLS lockdown complete 2026-07-30; anon writes revoked; cost tables service-role only).
- **`ssh wayway`** (Webuzo/Apache VPS; connection details in local ssh config): sites under `/home/bilal/public_html/<domain>/`. **Serving quirks (measured 2026-08-12):** apex/`www.wayway.ai` HTTPS is served by a *different origin* entirely; `versed.wayway.ai` resolves to this box but routes straight to the uvicorn worker app (`Server: uvicorn`) — Apache docroots are not reachable through either hostname, and the once-working `/audio/openiti-previews/.../manifest.json` currently 404s. Lab dashboard therefore lives on GitHub Pages, with a tailnet copy on hikma. Limited disk on `/` — do not stage corpora there.
- **hikma** (`/Volumes/hikma` locally ≡ `/mnt/hikma` on wayway; SMB from nautilus over Tailscale): 11TB, ~8.3TB free. Holds `OpenITI/`, `openiti-editions*`, `wayway-openiti-live-books/`, and now `versed-translator/`. Local mount can write files but not create root-level dirs — mkdir via `ssh wayway`.
- **`/Volumes/Nodes`** (local 11TB APFS, ~2TB free): `versed-translator/{scratch,models,corpus-cache}` — fast local scratch. The rest of the drive is personal backup data; never touch outside our subdir.

## 9. Residual Phase 0 verification (before C10 integration work)

- [ ] Read the exact current schema of `block_translations` and edition-scoped span tables (migrations), and the editions versioning semantics.
- [ ] Read `versed_core/jobs/runner.py` translation job handling end-to-end.
- [ ] Confirm where QE fields belong (extend `block_translations` vs. edition rows) with an idempotent migration draft.
- [ ] Confirm the Modal adapter interface conventions (`render_page_v2` pattern) to mirror for a translation model endpoint.
