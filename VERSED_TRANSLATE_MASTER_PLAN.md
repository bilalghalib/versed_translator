# Versed Translate: Master Build and Research Plan

You are helping build **Versed Translate**, an open, provenance-rich infrastructure for translating the Classical Arabic corpus into high-quality English at very large scale.

The long-term objective is not merely to run machine translation over OpenITI. We want to build an enduring open research and publishing system consisting of:

1. **Versed Parallel** — a rights-aware Arabic↔English parallel corpus assembled from existing human translations and later corrected machine translations.
2. **Versed Benchmark** — a frozen Classical Arabic→English evaluation set spanning major genres and periods.
3. **Versed Translate 27B** — a Classical Arabic-specialized translation model fine-tuned from TranslateGemma 27B.
4. **Versed-QE** — a translation-quality estimation and routing system using existing QE models plus Classical-Arabic-specific checks.
5. **Versed Align** — tooling to align existing English translations against Arabic source texts even when paragraph boundaries differ.
6. **The Translation Factory** — scalable inference, verification, repair, provenance, and publishing infrastructure.
7. **Versed Reader integration** — paragraph/block-level Arabic↔English alignment plus synchronized Arabic/English audio.
8. **Rights/provenance infrastructure** — enough information to distinguish public-domain/permissive texts, OpenITI-specific material, modern copyrighted translations, etc.
9. **An open/public project** — models, benchmarks, tools, and legally releasable texts should be openly shared where possible, while the hosted service, institutional work, commissioned processing, sponsorship, and other services can financially sustain the project and its maintainers.

We ultimately want to make a very large portion of the Islamic/Classical Arabic intellectual tradition:

* readable in Arabic;
* readable in good English;
* listenable;
* structurally aligned;
* searchable;
* machine-readable;
* provenance-aware;
* freely accessible where rights permit.

Do not optimize only for the first experiment. Build this as a staged system with explicit gates between phases.

---

# Core principles

### 1. Benchmark before specialization

Never fine-tune a model before establishing how the unmodified model performs on the same frozen benchmark.

We need to be able to answer:

> Did Versed Translate actually improve translation?

### 2. Test existing quality estimators before training our own

Start with established reference-free MT quality estimation systems such as:

* MetricX-QE;
* COMETKiwi;
* possibly other strong current QE systems if clearly relevant.

Do **not** assume we need a custom neural classifier.

Versed-QE should initially be a calibrated ensemble/router over existing QE scores plus deterministic fidelity checks.

Only train a specialized QE model if experimental evidence shows systematic Classical-Arabic blind spots.

### 3. Existing human translation beats regenerated translation

Before translating a work, determine whether a legally usable English translation already exists.

If so:

> align it rather than replace it.

Maintain 1:1, 1:N, and N:1 segment relationships.

### 4. Translator and evaluator must remain separate

Do not rely on the translation model grading itself.

The basic architecture is:

Arabic
→ translator
→ candidate English
→ independent QE + deterministic checks
→ accept / repair / human review.

### 5. Compute is cheap; errors at corpus scale are expensive

Bias toward quality.

We expect inference/fine-tuning costs to be low relative to:

* corpus preparation;
* rights research;
* alignment;
* evaluation;
* human correction;
* editorial work.

Do not sacrifice measurable translation quality merely to shave small amounts from GPU cost.

### 6. Preserve provenance at every step

Every English block should eventually be able to answer:

* where its Arabic came from;
* whether the underlying work is public domain;
* what digital source was used;
* whether OpenITI markup/metadata was retained;
* whether an existing human translation was used;
* which model/version generated the translation;
* QE scores;
* whether a repair model touched it;
* whether a human reviewed it;
* what TTS system generated its audio.

### 7. Never contaminate the benchmark

The frozen benchmark must never enter fine-tuning datasets, synthetic-data generation pools, or training-example retrieval.

---

# PHASE 0 — Repository and infrastructure orientation

Before modifying anything:

1. Inspect the existing Versed repositories, processing pipeline, database schema, OpenITI ingestion, job queues, Modal deployments, translation code, and audio pipeline.
2. Identify what already exists and should be extended rather than rebuilt.
3. Determine where translation jobs currently live in the pipeline.
4. Determine current canonical units:

   * book;
   * section;
   * block;
   * paragraph;
   * chunk;
   * translation;
   * audio segment.
5. Identify existing provenance fields.
6. Identify existing OpenITI source identifiers and upstream source information.
7. Document the current architecture in a short `VERSED_TRANSLATION_ARCHITECTURE.md`.

Do not undertake a large refactor just because another architecture would be cleaner.

Prefer thin additions around the working system.

**Gate:** We understand the current pipeline and know exactly where the translation subsystem attaches.

---

# PHASE 1 — Build Versed Benchmark v0

Create a frozen Classical Arabic→English evaluation corpus.

Initial target:

**2,000–5,000 passages.**

Do not optimize for sheer volume. Optimize for coverage and trustworthiness.

Include examples from:

* hadith;
* tafsir;
* sira;
* fiqh;
* usul al-fiqh;
* kalam/theology;
* philosophy;
* Sufism;
* history;
* biography;
* adab/literature;
* medicine/science;
* geography/travel;
* poetry where practical.

Include different historical periods and writing styles.

Include multiple passage sizes, approximately:

* short: 30–80 words;
* paragraph: 100–250 words;
* longer contextual passage: 250–600 words;
* selected near-context-limit examples.

Each benchmark item should contain where available:

```json
{
  "benchmark_id": "...",
  "work_id": "...",
  "author": "...",
  "genre": "...",
  "date_or_century": "...",
  "arabic": "...",
  "reference_english": "...",
  "translator": "...",
  "english_source": "...",
  "rights_status": "...",
  "notes": [],
  "benchmark_split": "test"
}
```

The English references may come from rights-safe human translations, research datasets usable for evaluation, or carefully manually curated examples.

The benchmark may include material that cannot be redistributed commercially if it can legally be used internally for evaluation, but rights status must be explicit.

Create versioned immutable releases:

`benchmark-v0.1`

`benchmark-v0.2`

etc.

Never silently change old benchmark items.

**Deliverable:** benchmark loader + dataset + statistics by genre/length/period.

**Gate:** We can run any translator against a stable set and obtain comparable outputs.

---

# PHASE 2 — Translation bakeoff

Build one common translation harness capable of running the same benchmark against multiple translation systems.

Initial candidates:

* TranslateGemma 27B;
* TranslateGemma 12B;
* Qwen-MT;
* Gemini Flash/Flash-Lite or strongest economically relevant Gemini translation setup;
* one strong frontier model as a rough quality ceiling if economically feasible.

TranslateGemma 27B is currently the leading candidate for the future Versed model.

Do not assume that generic benchmarks predict Classical Arabic performance.

For each run record:

```json
{
  "model": "...",
  "model_version": "...",
  "quantization": "...",
  "prompt_template": "...",
  "source_tokens": 0,
  "output_tokens": 0,
  "latency": 0,
  "batch_size": 0,
  "gpu": "...",
  "cost_estimate": 0,
  "translation": "..."
}
```

Keep prompts/templates version controlled.

Test paragraph-preserving structured output, e.g.:

```json
[
  {"id": "AR_001", "english": "..."},
  {"id": "AR_002", "english": "..."}
]
```

Send neighboring context when useful while requiring exact preservation of IDs.

Evaluate:

* omissions;
* additions/hallucinations;
* semantic reversals;
* negation;
* names;
* numbers;
* quotations;
* isnad chains;
* technical terminology;
* discourse coherence;
* readable English;
* paragraph fidelity.

**Deliverable:** comparison dataset and report.

**Gate:** We know which baseline translator is strongest for Classical Arabic and what quality difference exists between 12B and 27B.

---

# PHASE 3 — Real throughput/cost benchmark on Modal

Do not extrapolate corpus economics from single-request inference.

For TranslateGemma 27B benchmark actual **aggregate throughput under saturation**.

Test appropriate engines such as vLLM and/or SGLang.

Test GPU configurations such as:

* 1× H100;
* 2× H100 if useful;
* 4× H100;
* possibly L40S/H200 when economically relevant.

Measure across concurrency/batch levels such as:

1
8
32
64
128
256
512

and representative source lengths such as:

128
256
512
1024+ tokens.

Record:

* source/prefill tokens/sec;
* generated tokens/sec;
* total throughput;
* GPU utilization;
* GPU memory;
* wall-clock duration;
* startup overhead;
* batching efficiency;
* failure rate;
* dollars per million Arabic words;
* dollars per million English tokens.

Test BF16 baseline first where feasible, then:

* FP8;
* other quantizations that materially improve economics.

Compare output quality against BF16 before adopting quantization for production.

Do **not** assume the previously discussed hypothetical 22k output-token/sec result is real until measured.

**Deliverable:** reproducible Modal benchmark script + results.

**Gate:** We can estimate whole-corpus inference cost from measured data rather than speculation.

---

# PHASE 4 — Test existing QE systems

Do not build Versed-QE yet.

Run existing reference-free QE systems over every translation generated in Phase 2.

Initial models:

* MetricX-QE;
* COMETKiwi;
* any clearly superior current alternative discovered during implementation.

For each:

Arabic source

* machine translation
  → quality score.

Where reference English exists, also calculate appropriate reference-based metrics for analysis, but production routing must not depend on a reference.

Compare QE output against real errors/human/reference judgments.

Determine:

* precision for substantive translation failures;
* recall;
* calibration;
* performance by genre;
* performance by passage length;
* performance by model;
* failure types it misses.

---

# PHASE 5 — Adversarial/error-injection evaluation

Create controlled corrupted translations from high-quality benchmark examples.

Inject specific errors:

* delete a negation;
* change a number;
* omit a person;
* remove an isnad narrator;
* remove an entire clause;
* mistranslate a technical term;
* reverse agent/patient;
* hallucinate explanatory prose;
* omit a Qur'anic quotation;
* duplicate a sentence;
* leave Arabic untranslated;
* turn uncertainty into certainty;
* collapse two paragraphs;
* alter dates;
* alter citations.

Measure whether COMET/MetricX detect these.

This gives us much clearer information than passively evaluating naturally occurring errors.

Create an error taxonomy.

Example:

```text
OMISSION
ADDITION
NEGATION
ENTITY
NUMBER
TERMINOLOGY
QUOTATION
REFERENCE
STRUCTURE
COREFERENCE
REGISTER
FLUENCY
```

**Deliverable:** QE error-detection matrix.

**Gate:** We know precisely what existing QE can and cannot detect in Classical Arabic.

---

# PHASE 6 — Versed-QE v0

Only now implement Versed-specific quality routing.

Do not initially train a neural network.

Combine existing QE with deterministic/structural features.

Candidate features:

* MetricX score;
* COMET score;
* Arabic/English length ratio;
* named-entity coverage;
* numeric-token coverage;
* date coverage;
* quotation coverage;
* Qur'anic quotation matching;
* isnad/name-chain preservation;
* untranslated Arabic;
* repeated English;
* terminology consistency within work;
* segment completeness;
* translator/model identity;
* genre;
* period.

Initial output:

```text
ACCEPT
REPAIR
HUMAN_REVIEW
```

Optionally produce:

```json
{
  "p_publication_quality": 0.997,
  "p_substantive_error": 0.003,
  "reasons": []
}
```

Calibrate thresholds against held-out human/reference judgments.

Use a simple interpretable model first:

* logistic regression;
* gradient boosted trees;
* calibrated rule ensemble.

Only train a specialized neural QE model if simpler combinations fail materially.

The target should approximately mean:

> Probability that a competent bilingual editor would find no substantive translation error requiring correction.

Do not claim "99.5% safe" unless calibration supports that interpretation.

**Deliverable:** Versed-QE v0 + evaluation report.

**Gate:** We have measured accept/repair thresholds and know their expected error rates.

---

# PHASE 7 — Build Versed Parallel and rights/provenance pipeline

In parallel with the benchmarking work, construct a systematic inventory of existing translations.

For each Classical Arabic work, track:

```json
{
  "work_id": "...",
  "openiti_uri": "...",
  "canonical_title": "...",
  "author": "...",
  "arabic_source": "...",
  "arabic_source_provenance": "...",
  "english_translation": "...",
  "translator": "...",
  "publication_year": null,
  "english_source": "...",
  "rights_status": "...",
  "commercial_status": "...",
  "alignment_status": "...",
  "alignment_confidence": null
}
```

Search first for:

* public-domain translations;
* legally redistributable translations;
* parallel research corpora;
* hadith corpora;
* historical Oriental Translation Fund/Royal Asiatic Society material;
* Wikisource/Internet Archive/public libraries;
* direct permissions from translation rights holders.

Do not assume "online" means reusable.

Track rights independently for:

1. underlying medieval work;
2. digital Arabic source;
3. metadata/annotation;
4. English translation;
5. audio;
6. final database.

---

# PHASE 8 — OpenITI provenance strategy

Do not waste time manually re-OCRing books merely because OpenITI aggregates them.

OpenITI is extremely useful as discovery and source infrastructure.

However, distinguish:

* underlying public-domain Arabic;
* OpenITI-specific mARkdown/annotations;
* metadata;
* corpus/database organization;
* upstream digital sources.

Strip OpenITI-specific markup when it is not needed by Versed.

Create a provenance resolver that can record upstream source/library from OpenITI identifiers or metadata where available.

Example:

```text
OpenITI work
   ↓
canonical work identity
   ↓
upstream digital source
   ↓
normalized-text comparison
   ↓
Versed provenance record
```

Do not automatically classify every Arabic character retrieved through OpenITI as NC.

At the same time, do not assume that removing tags necessarily resolves database-right issues.

Prepare a concise rights question for OpenITI and eventually counsel covering:

* underlying public-domain strings;
* OpenITI annotations;
* corpus/database rights;
* commercial reuse;
* whether separate permission can be granted.

The system must be able to mark:

```text
COMMERCIAL_SAFE
COMMONS_ONLY
RESTRICTED
UNKNOWN
```

No book should enter commercial workflows without a known state.

---

# PHASE 9 — Versed Align

Existing English translations rarely share exact paragraph boundaries with OpenITI/Versed Arabic.

Build alignment supporting:

* 1:1;
* 1:N;
* N:1.

Use a staged alignment process:

1. normalize Arabic;
2. normalize English;
3. structural anchors:

   * chapter headings;
   * hadith numbers;
   * names;
   * dates;
   * Qur'anic references;
4. multilingual semantic embeddings;
5. monotonic sequence alignment;
6. LLM resolution only for ambiguous windows;
7. confidence scoring;
8. targeted human review.

Store alignment separately from source segmentation.

Example:

```text
AR_00421 → EN_00397

AR_00422 + AR_00423 → EN_00398

AR_00424 → EN_00399 + EN_00400
```

The reader may render these as one bilingual presentation unit even though source editions differ.

**Deliverable:** reusable alignment engine + confidence metrics.

---

# PHASE 10 — Assemble Versed Translate training corpus

Do not train on everything available.

Build a **high-quality, rights-safe training set**.

Initial target:

**100k–250k excellent parallel examples**, expanding later.

Prioritize diversity across:

* hadith;
* Qur'anic commentary;
* law;
* theology;
* philosophy;
* Sufism;
* history;
* literature/adab;
* biography;
* science;
* medicine;
* geography.

Thirty to fifty well-chosen books may be more useful than hundreds of highly repetitive ones.

Track:

* source work;
* genre;
* date;
* translator;
* rights;
* alignment confidence;
* human vs synthetic;
* revision history.

Deduplicate aggressively.

Do not include benchmark examples.

---

# PHASE 11 — Fine-tune Versed Translate 27B v0.1

Primary model target:

**TranslateGemma 27B → Versed Translate 27B**

Use LoRA/QLoRA initially unless evidence strongly supports full fine-tuning.

Run a controlled experiment series rather than one giant training job.

Variables may include:

* learning rate;
* LoRA rank;
* epochs;
* passage length;
* genre mixture;
* human-only vs human+synthetic training data;
* glossary conditioning;
* terminology instructions.

Log all experiments.

Evaluate every checkpoint on the frozen benchmark.

Compare directly against:

* base TranslateGemma 27B;
* TranslateGemma 12B;
* relevant API competitors.

Report improvements by genre and error category, not only aggregate score.

Examples:

```text
Hadith
Fiqh
Sufism
Philosophy
History
Adab
```

If fine-tuning does not materially improve the benchmark, stop and diagnose rather than scaling.

**Gate:** Versed Translate 27B demonstrably improves Classical Arabic translation without unacceptable regressions.

---

# PHASE 12 — Terminology and retrieval layer

After the first fine-tune, experiment with corpus-level terminology consistency.

Create a versioned glossary/terminology system capable of representing contextual rather than simplistic mappings.

Examples:

* nafs;
* ʿaql;
* walāya/wilāya;
* taqwā;
* fiqh;
* ḥaqīqa;
* maʿrifa;
* adab.

Do not force one English word per Arabic term.

Represent:

* domain;
* author/tradition;
* preferred translation;
* alternatives;
* transliteration policy;
* notes.

Evaluate whether retrieval-conditioned terminology improves consistency without making translation wooden.

---

# PHASE 13 — Cascade simulation

Before processing billions of words, simulate the production system using benchmark outputs.

For different Versed-QE thresholds estimate:

### Conservative

Small percentage auto-accepted.
Maximum quality.
Higher repair cost.

### Balanced

More auto-acceptance.

### Aggressive

Very high auto-acceptance.

For every threshold report:

* expected substantive-error rate;
* percentage auto-accepted;
* percentage repaired;
* percentage needing human review;
* compute cost;
* projected whole-corpus cost.

Find the cost-quality frontier.

Because inference is inexpensive, prefer a conservative threshold unless large-scale measurements justify otherwise.

---

# PHASE 14 — Repair model experiment

For translations rejected by Versed-QE, compare repair strategies.

Candidates:

* rerun Versed Translate 27B with error feedback;
* alternative decoding;
* stronger/future Versed checkpoint;
* Gemini/Qwen/frontier API;
* two-model comparison and synthesis.

Do not automatically use the most expensive model.

Record whether repair actually improves QE and human/reference measures.

The production loop should be:

```text
translation
    ↓
Versed-QE
    ↓
REPAIR
    ↓
repair model
    ↓
Versed-QE again
    ↓
accept or human review
```

Never infinitely retry.

---

# PHASE 15 — End-to-end pilot book

Do **not** go directly from benchmarks to the whole OpenITI corpus.

Select one substantial, difficult book, ideally:

**100k–500k+ Arabic words.**

Run the entire pipeline:

* ingest;
* clean;
* segment;
* provenance;
* existing-translation check;
* alignment if applicable;
* translation;
* QE;
* repair;
* audio;
* database insertion;
* reader rendering.

Measure real-world failures:

* malformed source;
* missing blocks;
* headers;
* poetry;
* footnotes;
* quotations;
* long paragraphs;
* repeated generations;
* truncation;
* model crashes;
* API/GPU errors;
* queue recovery;
* retries;
* resumability;
* database growth;
* audio alignment.

Manually sample at least ~100 random translations plus targeted edge cases.

**Gate:** A substantial book can pass through the system unattended with acceptable quality and recoverability.

---

# PHASE 16 — Production Translation Factory

Once the pilot passes, make the system corpus-scale.

Architecture:

```text
                         WORK
                          │
                existing translation?
                    /             \
                  yes              no
                   │                │
              Versed Align     Versed Translate 27B
                   │                │
                   └───────┬────────┘
                           ↓
                       Versed-QE
                      /    |     \
                  ACCEPT REPAIR HUMAN
                           │
                           ↓
                      score again
                           │
                           ↓
                       publication
```

Requirements:

* idempotent jobs;
* resumable batches;
* deterministic IDs;
* retries;
* checkpointing;
* cost ledger;
* model-version ledger;
* provenance;
* auditability;
* per-book progress;
* no duplicate work.

---

# PHASE 17 — Audio pipeline

For every approved Arabic/English presentation unit, generate audio according to rights-safe provider/model rules.

Arabic may use:

* Qur'anic recordings where separately licensed/appropriate;
* appropriate Arabic TTS;
* future specialized voices.

English may use:

* open/permissive TTS;
* commercially licensed hosted TTS;
* premium voices for supporters where rights permit.

Record:

```text
tts_model
tts_version
voice
voice_rights
generation_date
source_translation_version
commercial_status
```

If a translation changes, invalidate or regenerate dependent audio.

---

# PHASE 18 — Reader integration

The final Versed reader should support:

* Arabic;
* English;
* synchronized playback;
* highlighting current segment;
* paragraph/block alignment;
* provenance;
* translation source;
* confidence/review status where useful;
* multiple translations where available;
* search;
* bookmarks;
* notes.

Do not expose raw QE scores as if they were objective truth.

Prefer human-readable labels such as:

* Human translation
* Human-reviewed Versed translation
* Machine translation
* Machine translation, automatically verified

with deeper provenance available on demand.

---

# PHASE 19 — Feedback flywheel

Reader corrections and editorial corrections should become structured data.

Never automatically train on anonymous user edits.

Create a review path:

```text
reader report
    ↓
editorial verification
    ↓
accepted correction
    ↓
gold correction dataset
    ↓
future training corpus
```

Version translations.

Do not silently alter quoted/cited historical editions.

Over time:

Versed Translate v0.1
→ corrections
→ v0.2
→ more accepted translations
→ more corrections
→ v0.3.

Measure whether QE acceptance rate rises while benchmark quality also improves.

---

# PHASE 20 — Smaller public models

Only after establishing 27B performance, evaluate whether a smaller accessibility model is useful.

Potentially:

**Versed Translate 12B**

trained/distilled using:

* the same human corpus;
* carefully selected outputs from 27B;
* validated/corrected Versed data.

Eventually perhaps a 4B model.

The flagship remains 27B unless experiments demonstrate otherwise.

Release smaller versions because they are easier to run locally, not because we prematurely optimize compute.

---

# PHASE 21 — Open releases

Where rights permit, release:

### Versed Translate

Model weights/adapters and training methodology.

### Versed-QE

Quality-estimation/routing tooling.

### Versed Benchmark

Redistributable benchmark portions.

### Versed Parallel

Rights-safe Arabic↔English pairs with provenance.

### Versed Align

Alignment tools.

Document licenses separately.

Do not put a single blanket license over materials with different source rights.

---

# PHASE 22 — Sustainability/business infrastructure

The project should be designed as a public commons that can financially sustain the people doing the work.

The books themselves should remain broadly free wherever rights allow.

Potential revenue/support channels:

### Recurring supporters

People help keep the library free.

### Fund a Book

Readers or patrons fund translation/alignment/audio of specific works.

### Commission-to-Commons

An institution pays to digitize/translate a work and the resulting edition becomes publicly available where licensing permits.

### Institutional memberships

Libraries/universities pay for:

* hosted APIs;
* support;
* bulk workflows;
* researcher tooling;
* custom exports;
* integration;
* commissioned processing.

### Versed Studio

Paid processing for user-provided/public-domain books:

PDF
→ structured text
→ translation
→ QE
→ bilingual reader
→ audio.

### Grants/philanthropy

Position as:

* digital humanities;
* cultural preservation;
* open scholarly infrastructure;
* Classical Arabic NLP;
* translation research;
* accessible education;
* Islamic intellectual heritage.

The project's budget should explicitly include compensation for its maintainers/founding director.

Do not build an economic model in which "nonprofit/open" implicitly means unpaid labor.

---

# PHASE 23 — Rights-aware commercial architecture

Maintain at least these statuses:

```text
COMMERCIAL_SAFE
COMMONS_ONLY
RESTRICTED
UNKNOWN
```

Apply them independently to:

* Arabic source;
* English;
* audio;
* dataset distribution.

Possible architecture:

### Versed Commons

Freely available library and open infrastructure.

### Paid Versed services

Hosting, advanced functionality, compute, commissioned work, institutional access/support, APIs, optional premium audio/workspaces.

Do not rely on locking public-domain books behind a paywall as the primary business moat.

The moat is:

* corpus quality;
* alignment;
* provenance;
* coverage;
* audio;
* models;
* infrastructure;
* continuous maintenance;
* institutional reliability.

---

# PHASE 24 — Scale across OpenITI / Classical Arabic corpus

Only after all previous gates are demonstrated should we queue the large corpus.

Prioritize works strategically rather than translating arbitrary repository order.

Possible prioritization score:

```text
historical importance
+ reader demand
+ existing translation availability
+ rights clarity
+ genre coverage
+ translation difficulty
+ model-training value
+ audio value
```

Early releases should deliberately include diverse genres so that the system continues encountering new failure modes.

Maintain a public dashboard:

* works ingested;
* works translated;
* existing human translations aligned;
* words processed;
* audio hours;
* human-reviewed passages;
* QE acceptance rate;
* translation-model version;
* project funding;
* books currently seeking sponsorship.

---

# Implementation philosophy

For every phase:

1. inspect current implementation;
2. state the specific hypothesis being tested;
3. implement the smallest correct experiment;
4. collect real measurements;
5. document results;
6. decide whether evidence justifies moving forward;
7. preserve reproducibility;
8. do not replace measured findings with intuition.

Maintain a living document:

`VERSED_TRANSLATION_ROADMAP.md`

Each phase should show:

```text
STATUS
NOT STARTED / ACTIVE / COMPLETE / BLOCKED

QUESTION

IMPLEMENTATION

RESULTS

DECISION

NEXT DEPENDENCY
```

Also maintain:

`TRANSLATION_EXPERIMENTS.md`

with every benchmark/fine-tuning/QE experiment.

---

# Immediate execution order

The phases above describe the whole destination. The near-term work should proceed in this order:

```text
0. Inspect existing Versed pipeline
             ↓
1. Build frozen benchmark
             ↓
2. Build common translator harness
             ↓
3. Benchmark TG27/TG12/Qwen/Gemini
             ↓
4. Measure actual Modal throughput
             ↓
5. Run MetricX + COMETKiwi
             ↓
6. Run adversarial error tests
             ↓
7. Build minimal Versed-QE
             ↓
8. Build/expand parallel corpus + rights provenance
             ↓
9. Build alignment engine
             ↓
10. Assemble 100k–250k clean training pairs
             ↓
11. Fine-tune Versed Translate 27B v0.1
             ↓
12. Rerun frozen benchmark
             ↓
13. Build terminology layer if evidence supports it
             ↓
14. Simulate cascade thresholds
             ↓
15. Test repair strategies
             ↓
16. Run one substantial pilot book
             ↓
17. Harden production translation factory
             ↓
18. Integrate audio + reader
             ↓
19. Scale corpus progressively
             ↓
20. Release model/QE/alignment/data
             ↓
21. Continue correction → retraining flywheel
```

Several workstreams can happen in parallel:

```text
RESEARCH/ML
benchmark → bakeoff → QE → fine-tuning → cascade

CORPUS
rights inventory → existing translations → alignment → parallel dataset

INFRASTRUCTURE
Modal throughput → job system → provenance → production factory

PRODUCT
reader → aligned audio → provenance UI

SUSTAINABILITY
OpenITI permission/legal clarification
→ sponsorship
→ institutions
→ grants
→ paid services
```

Do not let one track block all others unnecessarily.

---

# Definition of success

The project succeeds when we can take an arbitrary Classical Arabic work and reliably determine:

1. what the work is;
2. where the Arabic came from;
3. whether an existing English translation can be legally reused;
4. whether to align or translate it;
5. how to produce a high-quality English translation;
6. how confident we are in that translation;
7. what needs automatic repair;
8. what genuinely needs human intervention;
9. how to generate aligned audio;
10. how to publish it with complete provenance;
11. whether each resulting layer can be used commercially or only in the commons;
12. how every correction improves future model versions.

The target is **not merely "translate OpenITI cheaply."**

The target is:

> **Build an open, sustainable translation infrastructure capable of making the Classical Arabic intellectual corpus readable and listenable in high-quality English, while preserving provenance, measuring uncertainty, improving over time, and financially supporting the people who maintain it.**

Use this destination when making local implementation decisions. Do not prematurely optimize away capabilities required by later phases.
