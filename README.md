# versed_translator

The translation **lab** for [Versed](https://versed.page) / [Wuquf](https://versed.page/wuquf): benchmark, bakeoff harness, quality-estimation router, alignment engine, training corpus, and fine-tuned Classical Arabic→English translation models — feeding the production factory in the `versed` repo.

**Read in this order:**

1. [`VERSED_TRANSLATE_MASTER_PLAN.md`](VERSED_TRANSLATE_MASTER_PLAN.md) — the destination (24 phases, principles, gates).
2. [`VERSED_TRANSLATION_ARCHITECTURE.md`](VERSED_TRANSLATION_ARCHITECTURE.md) — current state of the Versed system and where translation attaches.
3. [`VERSED_TRANSLATION_ROADMAP.md`](VERSED_TRANSLATION_ROADMAP.md) — **the working document**: component end states, checkpoints, decision queue, status.
4. [`TRANSLATION_EXPERIMENTS.md`](TRANSLATION_EXPERIMENTS.md) — append-only experiment ledger.

Planned layout (C0):

```
benchmark/   frozen Classical Arabic→English eval sets (immutable releases)
harness/     one interface to run any translator over any benchmark
qe/          QE evaluation, adversarial suite, Versed-QE router
align/       Versed Align — Ar↔En alignment engine (1:1, 1:N, N:1)
corpus/      rights inventory, provenance resolver, Versed Parallel, training sets
throughput/  Modal serving + measured economics
```

Core principles: benchmark before specialization; translator ≠ evaluator; existing human translation beats regeneration; provenance on everything; the frozen benchmark never touches training data.
