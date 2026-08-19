# versed_translator

**Start at [`STATUS.md`](STATUS.md)** — the only operational handoff. It carries current state, what's running, next steps, open decisions, and the traps already paid for.

Four documents, four jobs:

| File | Job |
| --- | --- |
| [`STATUS.md`](STATUS.md) | where we are, what's next — read this first |
| [`VERSED_TRANSLATE_MASTER_PLAN.md`](VERSED_TRANSLATE_MASTER_PLAN.md) | the destination and why (frozen; vision, not state) |
| [`TRANSLATION_EXPERIMENTS.md`](TRANSLATION_EXPERIMENTS.md) | every measurement with its caveats (append-only) |
| [`VERSED_TRANSLATION_ARCHITECTURE.md`](VERSED_TRANSLATION_ARCHITECTURE.md) | where translation attaches to the factory |

`VERSED_TRANSLATION_ROADMAP.md` holds component END STATEs and their `Verify:` checks — contracts, not status. Decisions are GitHub issues labelled `decision`. The dashboard is generated and authoritative for nothing.

[`CLAUDE.md`](CLAUDE.md) is the agent brief: standing rules, verification discipline, and how to run work without losing it. Read it before starting a coding session here.

The reusable Arabic-English zipper is documented in
[`docs/ALIGNMENT_BUNDLES.md`](docs/ALIGNMENT_BUNDLES.md). It emits deterministic
structural + paragraph + sentence alignment archives through `versed-align`;
it does not mutate Versed editions.

The reviewed algorithm, real Hamadhani results, and reproducible random
alignment examples are in
[`docs/ALIGNMENT_ALGORITHM_REVIEW.md`](docs/ALIGNMENT_ALGORITHM_REVIEW.md).

---
