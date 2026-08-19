# CLAUDE.md

## Read this first

**`STATUS.md` is the only operational handoff.** Read it before doing anything —
it carries current state, what's running, the next three things, and the traps
already paid for. Do not start from the roadmap.

This repo is the translation **lab** (`~/Projects/scripts/versed_translator`).
The production **factory** is a different repo, `~/Projects/scripts/versed`
(reader, VPS worker queue, Modal adapters, audio, wuquf). Work that belongs to
the factory goes there, not here.

Four documents, four jobs. Nothing else is a source of truth:

| File | Job |
| --- | --- |
| `STATUS.md` | where we are, what's next — read first |
| `VERSED_TRANSLATE_MASTER_PLAN.md` | the destination; **frozen** vision, never today's state |
| `TRANSLATION_EXPERIMENTS.md` | every measurement with its caveats; append-only |
| `VERSED_TRANSLATION_ARCHITECTURE.md` | where translation attaches to the factory |

`VERSED_TRANSLATION_ROADMAP.md` holds component END STATEs and their `Verify:`
checks — contracts that tell you when a component is done. It is a reference,
not a status board. Numbers live in the ledger, not the roadmap.

**Decisions are GitHub issues labelled `decision`**, not doc sections. The
dashboard under `docs/` is generated and authoritative for nothing.

## Standing rules

- **The frozen benchmark never touches training data.** Contamination is the
  one failure that invalidates everything downstream.
- **Translator ≠ evaluator.** Never let the model that produced a translation
  be the sole judge of it.
- **Provenance on everything** — work, genre, date, translator, rights,
  alignment confidence, human/synthetic flag. A pair without provenance is not
  usable.
- **Never mix `train_ok` English into `pd_english`.** Training on online English
  is an operator choice; shipping it in a released parallel dataset is not.
- **Never invent OpenITI URIs** for works absent from the inventory.
- Sunnah.com / hadith-json English is index-only: never ships, never trains.

## Verification

Evidence before assertions. A full row count, a clean exit, and a populated
file can all be false success — a 139-row run was once 139 `Connection refused`
errors, and the only tell was `wall_s: 0.06`. **Always check the error field and
a plausibility signal (wall time, token counts), never just row count.**

The same applies to background loops: judge them by what they produced, not by
whether they are alive. The harvest loop ticked for 25 hours after its consumer
died, and had already gone 16 passes without a single keeper.

```bash
uv run pytest
```

```bash
uv run ruff check .
```

Both must be green — CI runs exactly these on every push.

## Running work

- **Background jobs die with the session, and `nohup … & disown` is NOT enough**
  (verified twice). Use true session detachment —
  `subprocess.Popen([...], start_new_session=True)` — and `modal run --detach`
  so the Modal app survives the client CLI.
- Always write a `done-<job>` sentinel with the exit code into
  `~/versed-translator-data/logs/` so a fresh session can tell "finished" from
  "killed".
- **Do not restart the harvest loop expecting books.** Scraping for PD English
  is retired (2026-08-19): 13 keepers across 24 passes, zero in the last 16.
  Corpus growth runs through `corpus/rights_outreach.json` now.

## Storage

Never stage large data on the Mac's internal disk (it runs near-full). Prefer
`ssh nautilus`, where the 11TB disk is local at `/mnt/hikma`; the same volume is
an unreliable SMB mount at `/Volumes/hikma` on the Mac and has degraded
mid-session to `Permission denied` at the share root. Model weights live in the
Modal volume `versed-model-weights`.

## Working style

Define a verifiable end state, then iterate autonomously until `Verify:` passes.
Stop only at `[HUMAN]` gates — spend caps, rights, taste, outreach. Surface
decisions as GitHub issues or on the dashboard, never as a section in a document
for someone to find later.
