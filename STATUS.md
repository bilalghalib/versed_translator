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
- **Sources are not the constraint.** Catalog sweep (complete Gutenberg + archive.org) found Miskawayh 383 paragraphs ≥250 words, Suyuti 211, Payne's *Nights* 133–151 per volume × 10, Ibn Rushd at the best text quality measured. Miskawayh and Sachau's Biruni print Arabic page numbers inline — free hard anchors.

## What is running

- Block-level MetricX detection matrix — ~6,470 segments, detached. Sentinel `~/versed-translator-data/logs/done-metricx-blocks`. Tells us whether short blocks move *detection* rates; nothing above depends on it.

## Next 3 things

1. **A small genre-diverse benchmark — ~300–500 passages, 6–10 genres.** Enough that hadith stops dominating. Not the publication-grade set. Start with Miskawayh and Suyuti (long band + inline page anchors + isnad name density).
2. **Re-run TG12B vs TG27B on exactly that set with exactly the same structured prompt**, then **human-read 50–100 strategically chosen comparisons** — omissions, negations, technical vocabulary, long passages. chrF alone cannot decide this. Then choose 12B or 27B and record it.
3. **Pilot book.** One substantial work through the full path.

## Human decisions needed

**None open.** `gh issue list --label decision` is the live check; all six from 2026-08-14 are answered and closed.

The one standing ask, when the small benchmark exists: **label ~150–300 passages** "would a competent bilingual editor find a substantive error?" ⚠️ **Split it** — thresholds fitted on the same passages that report the router's accuracy is leakage. Calibration slice and eval slice must be disjoint.

## Known traps — do not re-derive

- A full row count, clean exit code and populated output file are **all compatible with total failure**. A 139-row run was 139 connection errors; the tell was `wall_s: 0.06`. Check the error field *and* a plausibility signal.
- **A metadata label is not evidence.** Both Modal legs recorded `prompt_template_id: "v1"` while sending something else; the bakeoff's headline comparison was confounded for a day and nothing failed.
- `nohup … & disown` does not survive session teardown, and **`setsid` does not exist on macOS**. Use `subprocess.Popen(..., start_new_session=True)` locally, `modal run --detach` for Modal, and write a `done-<job>` sentinel with the exit code.
- vLLM 0.11.0 allows `transformers` 5.x, which renamed `rope_scaling`. Pin `transformers<5`. Patching the model's `config.json` does **not** help — three attempts proved it, and a stale comment claiming otherwise was corrected.
- Sonnet 5's `max_tokens` caps thinking **plus** text; too small a budget returns empty translations.
- Local CPU inference for a 12B is ~2 tok/s. Inference happens on Modal.
- `/Volumes/hikma` (SMB) degrades mid-session to permission-denied at the share root. Read the corpus via `ssh nautilus` (`/mnt/hikma`).
- PDF rendering needs Homebrew's GTK stack: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib GI_TYPELIB_PATH=/opt/homebrew/lib/girepository-1.0 ~/mambaforge/bin/python`. Verify Arabic output **visually** — PyMuPDF `get_text()` returns visual order for RTL, so broken and correct look alike.

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
