#!/usr/bin/env python3
"""Granular Lamic prepare-path diagnosis. Stdlib-only through stage 6."""
from __future__ import annotations

import argparse
import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

BLOCKS_SQL = """
SELECT * FROM blocks
WHERE language='arabic' AND (? OR tts_skip=0)
  AND (audio_policy='tts'
       OR (? AND audio_policy='canonical_quran')
       OR (? AND audio_policy='skip'))
ORDER BY sequence
"""
BLOCKS_PARAMS = (0, 0, 0)  # include_skipped=False, include_quran=False

WORDS_SQL = """
SELECT
    w.*,
    a.diacritized_text,
    a.diacritics_source,
    a.diacritics_confidence,
    a.projection_status
FROM words w
LEFT JOIN word_analyses a ON a.word_id=w.id
WHERE w.block_id=?
ORDER BY w.sequence
"""

AUDIO_CHUNKS_SQL = """
SELECT id, status, source_hash, settings_hash,
       audio_sha256, audio_format, audio_relpath, json_relpath,
       duration_ms
FROM audio_chunks
"""

META_SQL = "SELECT value_json FROM edition_meta WHERE key=?"
COUNT_TIMEOUT_S = 45
SAMPLE_SIZES = (100, 1000, 10000)


def log(msg: str) -> None:
    print(msg, flush=True)


def now() -> float:
    return time.monotonic()


def read_proc_io(pid: int) -> dict[str, int]:
    out = {}
    try:
        for line in Path(f"/proc/{pid}/io").read_text().splitlines():
            k, v = line.split(":")
            out[k.strip()] = int(v.strip())
    except FileNotFoundError:
        pass
    return out


def read_stat_iowait() -> tuple[int, int]:
    """Return (iowait_ticks, total_ticks) from /proc/stat."""
    cpu = Path("/proc/stat").read_text().splitlines()[0].split()
    nums = [int(x) for x in cpu[1:]]
    iowait = nums[4] if len(nums) > 4 else 0
    return iowait, sum(nums)


class StageMon:
    def __init__(self, label: str, iostat_dev: str | None):
        self.label = label
        self.iostat_dev = iostat_dev
        self.proc: subprocess.Popen | None = None
        self.log_path: Path | None = None
        self.t0 = 0.0
        self.io0: dict[str, int] = {}
        self.cpu0 = (0.0, 0.0)
        self.wait0 = (0, 0)
        self.pid = os.getpid()

    def start(self) -> None:
        self.t0 = now()
        self.io0 = read_proc_io(self.pid)
        self.cpu0 = os.times()[:2]
        self.wait0 = read_stat_iowait()
        if self.iostat_dev:
            self.log_path = Path(f"/tmp/lamic-iostat-{self.label}-{self.pid}.txt")
            self.proc = subprocess.Popen(
                ["iostat", "-xz", self.iostat_dev, "1"],
                stdout=self.log_path.open("w"),
                stderr=subprocess.STDOUT,
            )

    def stop(self) -> None:
        wall = now() - self.t0
        io1 = read_proc_io(self.pid)
        cpu1 = os.times()[:2]
        wait1 = read_stat_iowait()
        if self.proc:
            self.proc.send_signal(signal.SIGINT)
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        rchar = io1.get("rchar", 0) - self.io0.get("rchar", 0)
        wchar = io1.get("wchar", 0) - self.io0.get("wchar", 0)
        read_bytes = io1.get("read_bytes", 0) - self.io0.get("read_bytes", 0)
        write_bytes = io1.get("write_bytes", 0) - self.io0.get("write_bytes", 0)
        user_s = cpu1[0] - self.cpu0[0]
        sys_s = cpu1[1] - self.cpu0[1]
        d_wait = wait1[0] - self.wait0[0]
        d_tot = max(1, wait1[1] - self.wait0[1])
        iowait_pct = 100.0 * d_wait / d_tot
        log(
            f"  mon wall_s={wall:.3f} cpu_user_s={user_s:.3f} cpu_sys_s={sys_s:.3f} "
            f"cpu_pct={100*(user_s+sys_s)/max(wall,0.001):.0f} "
            f"host_iowait_pct={iowait_pct:.0f} "
            f"rchar_mb={rchar/1e6:.1f} read_mb={read_bytes/1e6:.1f} "
            f"wchar_mb={wchar/1e6:.1f} write_mb={write_bytes/1e6:.1f}"
        )
        if self.log_path and self.log_path.exists():
            lines = [
                ln
                for ln in self.log_path.read_text().splitlines()
                if ln.startswith(self.iostat_dev or "___")
            ]
            if lines:
                log(f"  iostat {self.iostat_dev} samples={len(lines)} last={lines[-1]}")
                util = []
                await_ms = []
                for ln in lines:
                    parts = ln.split()
                    if len(parts) >= 14:
                        try:
                            await_ms.append(float(parts[9]))
                            util.append(float(parts[-1]))
                        except ValueError:
                            pass
                if util:
                    log(
                        f"  iostat_summary await_ms_avg={sum(await_ms)/len(await_ms):.1f} "
                        f"util_avg={sum(util)/len(util):.0f} util_max={max(util):.0f}"
                    )


def open_ro(db: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA busy_timeout=15000")
    return con


def stage_open(db: Path, iostat_dev: str | None) -> None:
    log("=== STAGE 1 open SQLite (no COUNT) ===")
    log(f"BEFORE sqlite3.connect mode=ro {db}")
    mon = StageMon("open", iostat_dev)
    mon.start()
    t = now()
    con = open_ro(db)
    log(f"AFTER open_ro s={now()-t:.3f}")
    t = now()
    con.execute("SELECT 1").fetchone()
    log(f"AFTER SELECT 1 s={now()-t:.3f}")
    mon.stop()
    con.close()


def stage_meta(db: Path, iostat_dev: str | None) -> None:
    log("=== STAGE 2 cheap metadata (no table scans) ===")
    log(f"BEFORE schema/pragma {db}")
    mon = StageMon("meta", iostat_dev)
    mon.start()
    con = open_ro(db)
    t = now()
    page_count = con.execute("PRAGMA page_count").fetchone()[0]
    page_size = con.execute("PRAGMA page_size").fetchone()[0]
    page_free = con.execute("PRAGMA freelist_count").fetchone()[0]
    log(
        f"AFTER pragma page_count/page_size/freelist s={now()-t:.3f} "
        f"page_count={page_count} page_size={page_size} "
        f"file_mb={page_count*page_size/1e6:.1f} freelist={page_free} "
        f"stat_mb={db.stat().st_size/1e6:.1f}"
    )
    t = now()
    tables = list(
        con.execute(
            "SELECT type, name, tbl_name FROM sqlite_master "
            "WHERE type IN ('table','index') ORDER BY type, name"
        )
    )
    log(f"AFTER sqlite_master s={now()-t:.3f} objects={len(tables)}")
    for typ, name, tbl in tables:
        log(f"  {typ:5} {name} -> {tbl}")
    t = now()
    for tbl in ("blocks", "words", "word_analyses", "audio_chunks", "edition_meta"):
        info = list(con.execute(f"PRAGMA table_info({tbl})"))
        idx = list(con.execute(f"PRAGMA index_list({tbl})"))
        log(f"  table_info {tbl} cols={len(info)} indexes={[r[1] for r in idx]}")
    log(f"AFTER pragma table_info/index_list s={now()-t:.3f}")
    t = now()
    row = con.execute(META_SQL, ("book_uri",)).fetchone()
    log(f"AFTER edition_meta book_uri s={now()-t:.3f} value={row[0] if row else None}")
    # dbstat walks pages — do not treat as cheap. Skip.
    log("SKIP dbstat (page walk / scan; not cheap metadata)")
    mon.stop()
    con.close()


def _count_one(db: str, sql: str, q) -> None:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30)
    t = time.monotonic()
    n = con.execute(sql).fetchone()[0]
    q.put((n, time.monotonic() - t))


def stage_counts(db: Path, iostat_dev: str | None) -> None:
    log("=== STAGE 3 COUNT(*) separately (timeout %ds) ===" % COUNT_TIMEOUT_S)
    import multiprocessing as mp

    queries = [
        "SELECT COUNT(*) FROM blocks",
        "SELECT COUNT(*) FROM words",
        "SELECT COUNT(*) FROM word_analyses",
        "SELECT COUNT(*) FROM audio_chunks",
    ]
    ctx = mp.get_context("fork")
    for sql in queries:
        log(f"BEFORE {sql}")
        mon = StageMon("count", iostat_dev)
        mon.start()
        q: mp.Queue = ctx.Queue()
        p = ctx.Process(target=_count_one, args=(str(db), sql, q))
        p.start()
        p.join(COUNT_TIMEOUT_S)
        if p.is_alive():
            p.terminate()
            p.join(3)
            if p.is_alive():
                p.kill()
                p.join(1)
            log(
                f"AFTER TIMEOUT {COUNT_TIMEOUT_S}s — aborted {sql} "
                "(COUNT itself is expensive; skipping remaining COUNTs on this arm)"
            )
            mon.stop()
            return
        n, secs = q.get(timeout=2)
        log(f"AFTER {sql} n={n} s={secs:.3f}")
        mon.stop()


def explain(con: sqlite3.Connection, sql: str, params=()) -> None:
    log(f"EXPLAIN QUERY PLAN :: {sql.strip()[:180]}")
    t = now()
    rows = list(con.execute("EXPLAIN QUERY PLAN " + sql, params))
    log(f"  explain_s={now()-t:.3f}")
    for row in rows:
        log(f"  {tuple(row)}")


def stage_explain(db: Path, iostat_dev: str | None) -> str | None:
    log("=== STAGE 4 EXPLAIN production prepare queries (no full prepare) ===")
    log("Production path: index_book -> connect_ledger (RW/WAL/schema) -> _audio_jobs")
    log("  1x BLOCKS_SQL, then N times WORDS_SQL per arabic block, then 1x AUDIO_CHUNKS_SQL")
    mon = StageMon("explain", iostat_dev)
    mon.start()
    log("BEFORE open_ro for EXPLAIN")
    t = now()
    con = open_ro(db)
    log(f"AFTER open_ro s={now()-t:.3f}")
    log("BEFORE SELECT id FROM blocks LIMIT 1 (need a real block_id)")
    t = now()
    row = con.execute("SELECT id FROM blocks LIMIT 1").fetchone()
    bid = row[0] if row else "missing"
    log(f"AFTER LIMIT 1 s={now()-t:.3f} block_id={bid}")
    explain(con, BLOCKS_SQL, BLOCKS_PARAMS)
    explain(con, WORDS_SQL, (bid,))
    explain(con, AUDIO_CHUNKS_SQL)
    explain(con, META_SQL, ("book_uri",))
    explain(
        con,
        "SELECT id FROM blocks WHERE language='arabic' ORDER BY sequence",
    )
    mon.stop()
    con.close()
    return bid


def pct(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    ys = sorted(xs)
    i = min(len(ys) - 1, max(0, round((p / 100) * (len(ys) - 1))))
    return ys[i]


def stage_nplusone_probe(db: Path, iostat_dev: str | None, n_probe: int = 100) -> None:
    log("=== STAGE 5 N+1 probe: query count x latency on first %d blocks ===" % n_probe)
    log(f"SQL={WORDS_SQL.strip()}")
    mon = StageMon("nplusone", iostat_dev)
    mon.start()
    log("BEFORE fetch block ids LIMIT %d" % n_probe)
    t = now()
    con = open_ro(db)
    ids = [
        r[0]
        for r in con.execute(
            "SELECT id FROM blocks WHERE language='arabic' AND tts_skip=0 "
            "AND audio_policy='tts' ORDER BY sequence LIMIT ?",
            (n_probe,),
        )
    ]
    log(f"AFTER block-id fetch s={now()-t:.3f} n={len(ids)}")
    lat = []
    words = 0
    log(f"BEFORE {len(ids)} per-block WORDS_SQL")
    t = now()
    for i, bid in enumerate(ids):
        t1 = now()
        rows = con.execute(WORDS_SQL, (bid,)).fetchall()
        lat.append(now() - t1)
        words += len(rows)
        if i + 1 in (1, 10, 50, 100) or (i + 1) == len(ids):
            log(
                f"  progress i={i+1} last_s={lat[-1]*1000:.1f}ms words_this={len(rows)} "
                f"words_cum={words}"
            )
    total = now() - t
    log(
        f"AFTER N+1 n_queries={len(lat)} words={words} total_s={total:.3f} "
        f"avg_ms={1000*sum(lat)/max(len(lat),1):.2f} "
        f"p50_ms={1000*pct(lat,50):.2f} p95_ms={1000*pct(lat,95):.2f} "
        f"max_ms={1000*max(lat, default=0):.2f} "
        f"qps={len(lat)/max(total,0.001):.1f}"
    )
    log(
        "N+1_CONFIRMED production _audio_jobs executes WORDS_SQL once per block "
        f"(~{len(ids)} times in this probe; full book is one query per arabic block)"
    )
    mon.stop()
    con.close()


def extract_n(con: sqlite3.Connection, n: int) -> tuple[list, int]:
    log(f"BEFORE BLOCKS_SQL LIMIT {n}")
    t = now()
    blocks = list(
        con.execute(
            BLOCKS_SQL + " LIMIT ?",
            BLOCKS_PARAMS + (n,),
        )
    )
    log(f"AFTER BLOCKS_SQL n={len(blocks)} s={now()-t:.3f}")
    words = 0
    log(f"BEFORE per-block WORDS_SQL x {len(blocks)}")
    t = now()
    last = t
    for i, block in enumerate(blocks):
        rows = con.execute(WORDS_SQL, (block["id"],)).fetchall()
        words += len(rows)
        if (i + 1) % max(1, n // 5) == 0 or (i + 1) == len(blocks):
            log(
                f"  extract progress blocks={i+1}/{len(blocks)} words={words} "
                f"dt={now()-last:.2f}s elapsed={now()-t:.2f}s"
            )
            last = now()
    log(f"AFTER extract blocks={len(blocks)} words={words} s={now()-t:.3f}")
    return blocks, words


def stage_extract_samples(db: Path, iostat_dev: str | None) -> None:
    log("=== STAGE 6 extraction samples 100 / 1000 / 10000 (no payload, no upsert) ===")
    con = open_ro(db)
    for n in SAMPLE_SIZES:
        log(f"--- extract n={n} ---")
        mon = StageMon(f"extract{n}", iostat_dev)
        mon.start()
        extract_n(con, n)
        mon.stop()
    con.close()


def stage_payload_samples(db: Path, book: Path, iostat_dev: str | None) -> None:
    log("=== STAGE 7 payload/audio-job construction on same samples (no upsert) ===")
    log("BEFORE import versed_core (taxonomy warnings expected)")
    t = now()
    sys.path.insert(0, "/home/bilal/versed-ingest/versed-app")
    from versed_core.audio.openiti_catalog_sync import (
        audio_job_payload,
        encode_job_payload,
    )
    from versed_core.audio.openiti_editions import (
        AudioJob,
        _audio_jobs,
        _get_meta,
        _spoken_word,
        canonical_json,
        sha256_text,
        split_word_ranges,
        stable_id,
    )
    from versed_core.enrichment.arabic_word_analysis import normalize_arabic
    from versed_core.expansions.honorifics import ISLAMIC_PHRASE_DETECTOR_VERSION

    log(f"AFTER import s={now()-t:.3f}")

    settings = {
        "language": "ar",
        "voice_id": "1c3294e9c96b47dc8621dc8b2283bc97",
        "model_id": "s2.1-pro-free",
        "latency": "normal",
        "max_chars": 700,
        "include_quran_tts": False,
        "max_chunks": None,
        "text_projection": "diacritized",
        "include_skipped_tts": False,
    }

    def jobs_from_n_blocks(con: sqlite3.Connection, n: int) -> list:
        """Same grouping/join/hash as _audio_jobs, but stop after n source blocks."""
        block_rows = list(con.execute(BLOCKS_SQL + " LIMIT ?", BLOCKS_PARAMS + (n,)))
        book_uri = _get_meta(con, "book_uri")
        settings_payload = {
            "provider": "fish",
            "model_id": settings["model_id"],
            "voice_id": settings["voice_id"],
            "latency": settings["latency"],
            "normalize": True,
            "max_chars": settings["max_chars"],
            "language": settings["language"],
            "text_projection": settings["text_projection"],
        }
        settings_hash = sha256_text(canonical_json(settings_payload))
        speech_groups: list[list] = []
        for block in block_rows:
            is_continuation = str(block["text"] or "").lstrip().startswith("~~")
            if is_continuation and speech_groups:
                speech_groups[-1].append(block)
            else:
                speech_groups.append([block])
        jobs = []
        for group in speech_groups:
            source_words = []
            omitted = []
            hash_parts = []
            included = []
            for block in group:
                block_words = [dict(row) for row in con.execute(WORDS_SQL, (block["id"],))]
                missing = [
                    w["id"]
                    for w in block_words
                    if w.get("language") == "arabic"
                    and normalize_arabic(str(w.get("text") or ""))
                    and not w.get("diacritized_text")
                ]
                if missing:
                    raise RuntimeError(
                        f"missing diacritics block={block['id']} n={len(missing)}"
                    )
                block_words = [
                    {
                        **w,
                        "spoken_text": (
                            w.get("spoken_text")
                            if w.get("semantic_source") == ISLAMIC_PHRASE_DETECTOR_VERSION
                            else w.get("diacritized_text") or w.get("spoken_text")
                        ),
                    }
                    for w in block_words
                ]
                hash_parts.append(
                    [block["id"], [[w["id"], _spoken_word(w)] for w in block_words]]
                )
                included.append(block)
                for w in block_words:
                    if not _spoken_word(w).strip():
                        omitted.append(str(w["id"]))
                        continue
                    source_words.append({**w, "audio_sequence": len(source_words)})
            if not source_words or not included:
                continue
            first, last = included[0], included[-1]
            block_ids = tuple(str(b["id"]) for b in included)
            source_hash = sha256_text(canonical_json(hash_parts))
            for start, end in split_word_ranges(source_words, max_chars=700):
                chunk_words = tuple(source_words[start:end])
                tts_text = " ".join(_spoken_word(w) for w in chunk_words).strip()
                if not tts_text:
                    continue
                chunk_id = stable_id(
                    "c",
                    book_uri,
                    "ar",
                    canonical_json(block_ids),
                    start,
                    end,
                    source_hash,
                    settings_hash,
                    length=32,
                )
                jobs.append(
                    AudioJob(
                        chunk_id=chunk_id,
                        book_uri=book_uri,
                        book_dir=book,
                        language="ar",
                        block_id=str(first["id"]),
                        block_ids=block_ids,
                        block_sequence=int(first["sequence"]),
                        source_hash=source_hash,
                        source_word_start=start,
                        source_word_end=end,
                        words=chunk_words,
                        omitted_word_ids=tuple(omitted),
                        tts_text=tts_text,
                        voice_id=settings["voice_id"],
                        model_id=settings["model_id"],
                        latency=settings["latency"],
                        settings_hash=settings_hash,
                        text_projection="diacritized",
                        pause_before_ms=int(first["pause_before_ms"]) if start == 0 else 0,
                        pause_after_ms=int(last["pause_after_ms"])
                        if end == len(source_words)
                        else 0,
                    )
                )
        return jobs

    con = open_ro(db)
    for n in SAMPLE_SIZES:
        log(f"--- payload n={n} ---")
        mon = StageMon(f"payload{n}", iostat_dev)
        mon.start()
        log(f"BEFORE construct jobs n={n}")
        t = now()
        jobs = jobs_from_n_blocks(con, n)
        construct_s = now() - t
        log(f"AFTER construct jobs={len(jobs)} s={construct_s:.3f}")
        log(f"BEFORE encode_job_payload x {len(jobs)}")
        t = now()
        blobs = [encode_job_payload(audio_job_payload(j)) for j in jobs]
        enc_s = now() - t
        nbytes = sum(len(b) for b in blobs)
        log(
            f"AFTER encode s={enc_s:.3f} jobs={len(jobs)} payload_bytes={nbytes} "
            f"avg_bytes={nbytes/max(len(blobs),1):.0f}"
        )
        mon.stop()
    con.close()
    log("NOTE _audio_jobs imported but full-book call is stage 8 only")
    _ = _audio_jobs


def stage_connect_ledger(book: Path, iostat_dev: str | None) -> None:
    log("=== STAGE 4b production connect_ledger (RW/WAL/schema, then close) ===")
    log("This is what index_book does before _audio_jobs. Live queue untouched.")
    sys.path.insert(0, "/home/bilal/versed-ingest/versed-app")
    log("BEFORE import connect_ledger")
    t = now()
    from versed_core.audio.openiti_editions import connect_ledger

    log(f"AFTER import connect_ledger s={now()-t:.3f}")
    mon = StageMon("connect_ledger", iostat_dev)
    mon.start()
    log(f"BEFORE connect_ledger {book}")
    t = now()
    ledger = connect_ledger(book)
    log(f"AFTER connect_ledger s={now()-t:.3f}")
    t = now()
    uri = ledger.execute(
        "SELECT value_json FROM edition_meta WHERE key=?", ("book_uri",)
    ).fetchone()
    log(f"AFTER meta via ledger s={now()-t:.3f} uri={uri[0] if uri else None}")
    ledger.close()
    log("AFTER close")
    mon.stop()


def stage_full(book: Path, db: Path, iostat_dev: str | None) -> None:
    log("=== STAGE 8 full _audio_jobs + encode (no coordinator upsert) ===")
    sys.path.insert(0, "/home/bilal/versed-ingest/versed-app")
    from versed_core.audio.openiti_catalog_sync import (
        audio_job_payload,
        encode_job_payload,
    )
    from versed_core.audio.openiti_editions import _audio_jobs, connect_ledger

    settings = {
        "language": "ar",
        "voice_id": "1c3294e9c96b47dc8621dc8b2283bc97",
        "model_id": "s2.1-pro-free",
        "latency": "normal",
        "max_chars": 700,
        "include_quran_tts": False,
        "max_chunks": None,
        "text_projection": "diacritized",
        "include_skipped_tts": False,
    }
    mon = StageMon("full", iostat_dev)
    mon.start()
    log("BEFORE connect_ledger for full run")
    t = now()
    ledger = connect_ledger(book)
    log(f"AFTER connect_ledger s={now()-t:.3f}")
    try:
        log("BEFORE _audio_jobs full book")
        t = now()
        jobs = _audio_jobs(ledger, book, **settings)
        log(f"AFTER _audio_jobs jobs={len(jobs)} s={now()-t:.3f}")
    finally:
        ledger.close()
    log(f"BEFORE encode x {len(jobs)}")
    t = now()
    blobs = [encode_job_payload(audio_job_payload(j)) for j in jobs]
    log(
        f"AFTER encode s={now()-t:.3f} payload_bytes={sum(len(b) for b in blobs)}"
    )
    mon.stop()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--book", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--iostat-dev", default=None)
    ap.add_argument("--upto", type=int, default=7)
    ap.add_argument("--only", type=int, default=0)
    args = ap.parse_args()
    db = Path(args.db)
    book = Path(args.book)
    log(f"=== Lamic prepare bench label={args.label} pid={os.getpid()} ===")
    log(f"db={db} exists={db.exists()} size_mb={db.stat().st_size/1e6:.1f}")
    log(f"book={book} iostat_dev={args.iostat_dev} upto={args.upto}")
    log("Linux caches NOT dropped")
    stages = {
        1: lambda: stage_open(db, args.iostat_dev),
        2: lambda: stage_meta(db, args.iostat_dev),
        3: lambda: stage_counts(db, args.iostat_dev),
        4: lambda: stage_explain(db, args.iostat_dev),
        5: lambda: stage_nplusone_probe(db, args.iostat_dev),
        6: lambda: stage_extract_samples(db, args.iostat_dev),
        7: lambda: (
            stage_connect_ledger(book, args.iostat_dev),
            stage_payload_samples(db, book, args.iostat_dev),
        ),
        8: lambda: stage_full(book, db, args.iostat_dev),
    }
    wanted = [args.only] if args.only else list(range(1, args.upto + 1))
    for n in wanted:
        log(f"\n######## START STAGE {n} arm={args.label} ########")
        stages[n]()
        log(f"######## END STAGE {n} arm={args.label} ########")
    log(f"DONE upto={args.upto} only={args.only} label={args.label}")


if __name__ == "__main__":
    main()
