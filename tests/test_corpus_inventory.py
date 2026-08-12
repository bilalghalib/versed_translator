"""Unit tests for C6 checkpoints 1-2: works inventory + provenance resolver v0.

All fixtures are inline/small — no reads against the SMB-mounted OpenITI
share, so these tests run anywhere.
"""

from __future__ import annotations

from versed_translator.corpus import inventory, resolver

# --- resolver: author_death_ah ------------------------------------------------


def test_resolve_death_ah_from_uri_prefix():
    result = resolver.resolve("0505Ghazali.Tahafut", meta=None)
    assert result["author_death_ah"] == 505
    assert result["evidence"]["author_death_ah"] == "uri_prefix"


def test_resolve_death_ah_placeholder_year_still_read_from_uri():
    # OpenITI uses "0001" for undated/anonymous authors; the resolver reports
    # what it finds and lets callers interpret the placeholder.
    result = resolver.resolve("0001AwsIbnHajar.Diwan", meta=None)
    assert result["author_death_ah"] == 1
    assert result["evidence"]["author_death_ah"] == "uri_prefix"


def test_resolve_death_ah_falls_back_to_meta_when_uri_has_no_prefix():
    result = resolver.resolve("AnonymousWork.NoYearPrefix", meta={"death_ah": 400})
    assert result["author_death_ah"] == 400
    assert result["evidence"]["author_death_ah"] == "meta.death_ah"


def test_resolve_death_ah_unresolved_without_uri_prefix_or_meta():
    result = resolver.resolve("AnonymousWork.NoYearPrefix", meta=None)
    assert result["author_death_ah"] is None
    assert result["evidence"]["author_death_ah"] is None


# --- resolver: source_lib_claim ------------------------------------------------


def test_resolve_source_lib_from_meta_url_shamela():
    meta = {
        "url": (
            "https://raw.githubusercontent.com/OpenITI/0200AH/master/data/"
            "0179MalikIbnAnas/0179MalikIbnAnas.Muwatta/"
            "0179MalikIbnAnas.Muwatta.Shamela0028107-ara1.completed"
        )
    }
    result = resolver.resolve("0179MalikIbnAnas.Muwatta", meta=meta)
    assert result["source_lib_claim"] == "Shamela"
    assert result["evidence"]["source_lib_claim"] == "meta.url_tail"


def test_resolve_source_lib_from_meta_url_jk_no_extension():
    meta = {
        "url": (
            "https://raw.githubusercontent.com/OpenITI/0025AH/master/data/"
            "0001AwsIbnHajar/0001AwsIbnHajar.Diwan/"
            "0001AwsIbnHajar.Diwan.JK007502-ara1"
        )
    }
    result = resolver.resolve("0001AwsIbnHajar.Diwan", meta=meta)
    assert result["source_lib_claim"] == "JK"
    assert result["evidence"]["source_lib_claim"] == "meta.url_tail"


def test_resolve_source_lib_from_uri_tail_when_no_meta():
    # Caller passes an already-versioned URI string directly (no metadata
    # lookup available/needed).
    result = resolver.resolve("0200AbuGhanimKhurasani.MudawwanaKubra.ShamIbadiyya0000772-ara1", meta=None)
    assert result["source_lib_claim"] == "ShamIbadiyya"
    assert result["evidence"]["source_lib_claim"] == "uri_tail"


def test_resolve_source_lib_uri_without_source_tail_is_unresolved():
    # A bare catalog URI (author.title, no version tail) and no metadata:
    # there is nothing to extract a source claim from.
    result = resolver.resolve("0505Ghazali.Tahafut", meta=None)
    assert result["source_lib_claim"] is None
    assert result["evidence"]["source_lib_claim"] is None


def test_resolve_source_lib_meta_present_but_url_missing_falls_back_to_uri():
    result = resolver.resolve("0505Ghazali.Tahafut", meta={"title": "x"})
    assert result["source_lib_claim"] is None
    assert result["evidence"]["source_lib_claim"] is None


# --- resolver: evidence shape --------------------------------------------------


def test_resolve_evidence_shape():
    meta = {
        "url": "https://x/0505Ghazali.Tahafut.Shamela0011055-ara1",
        "death_ah": 505,
    }
    result = resolver.resolve("0505Ghazali.Tahafut", meta=meta)
    assert set(result.keys()) == {"work_uri", "author_death_ah", "source_lib_claim", "evidence"}
    assert result["work_uri"] == "0505Ghazali.Tahafut"
    assert set(result["evidence"].keys()) == {"author_death_ah", "source_lib_claim"}
    for value in result["evidence"].values():
        assert value is None or isinstance(value, str)


# --- inventory: priority list parsing ------------------------------------------


def test_load_priority_uris_skips_comments_and_blanks(tmp_path):
    p = tmp_path / "priority.txt"
    p.write_text(
        "# header comment\n"
        "# another comment line\n"
        "\n"
        "0179MalikIbnAnas.Muwatta\n"
        "0676Nawawi.ArbacunaNawawiyya\n"
        "\n"
        "0255Jahiz.Hayawan\n"
    )
    uris = inventory.load_priority_uris(p)
    assert uris == [
        "0179MalikIbnAnas.Muwatta",
        "0676Nawawi.ArbacunaNawawiyya",
        "0255Jahiz.Hayawan",
    ]


def test_load_priority_uris_preserves_order_as_rank(tmp_path):
    p = tmp_path / "priority.txt"
    p.write_text("first.uri\nsecond.uri\nthird.uri\n")
    uris = inventory.load_priority_uris(p)
    assert uris.index("first.uri") < uris.index("second.uri") < uris.index("third.uri")


# --- inventory: build_work_row (meta loaded from a fake OpenITI_DIR) ----------


def test_build_work_row_meta_found(tmp_path):
    meta_dir = tmp_path / "meta"
    meta_dir.mkdir()
    (meta_dir / "0505Ghazali.Tahafut.json").write_text(
        '{"uri": "0505Ghazali.Tahafut", '
        '"url": "https://x/0505Ghazali.Tahafut.Shamela0011055-ara1", '
        '"title_en": "Tahafut", "author_en": "Ghazali", '
        '"death_ah": 505, "tags": ["Philosophy"]}'
    )
    row = inventory.build_work_row("0505Ghazali.Tahafut", priority_rank=1, openiti_dir=tmp_path)
    assert row["meta_found"] is True
    assert row["author"] == "Ghazali"
    assert row["title"] == "Tahafut"
    assert row["author_death_ah"] == 505
    assert row["source_lib_claim"] == "Shamela"
    assert row["genre"] == "Philosophy"
    assert row["arabic_rights"] == "UNKNOWN"
    assert row["english_rights"] == "UNKNOWN"
    assert row["commercial_status"] == "UNKNOWN"
    assert row["priority_rank"] == 1


def test_build_work_row_meta_missing(tmp_path):
    (tmp_path / "meta").mkdir()
    row = inventory.build_work_row("9999NoSuch.Work", priority_rank=7, openiti_dir=tmp_path)
    assert row["meta_found"] is False
    assert row["author"] is None
    assert row["title"] is None
    # death_ah still resolves from the URI prefix even without metadata.
    assert row["author_death_ah"] == 9999
    assert row["source_lib_claim"] is None


# --- inventory: build_inventory + stats end to end (small local fixture) ------


def _write_priority_list(tmp_path, uris):
    p = tmp_path / "priority.txt"
    p.write_text("# header\n" + "\n".join(uris) + "\n")
    return p


def _write_meta(meta_dir, uri, **fields):
    import json

    (meta_dir / f"{uri}.json").write_text(json.dumps({"uri": uri, **fields}))


def test_build_inventory_and_stats_end_to_end(tmp_path):
    meta_dir = tmp_path / "meta"
    meta_dir.mkdir()

    _write_meta(
        meta_dir,
        "0505Ghazali.Tahafut",
        url="https://x/0505Ghazali.Tahafut.Shamela0011055-ara1",
        title_en="Tahafut",
        author_en="Ghazali",
        death_ah=505,
        tags=["Philosophy"],
    )
    _write_meta(
        meta_dir,
        "0001AwsIbnHajar.Diwan",
        url="https://x/0001AwsIbnHajar.Diwan.JK007502-ara1",
        title_en="Diwan",
        author_en="Aws Ibn Hajar",
        death_ah=1,
        tags=[],
    )
    # third URI intentionally has no metadata file -> meta_found False

    priority_list = _write_priority_list(
        tmp_path,
        ["0505Ghazali.Tahafut", "0001AwsIbnHajar.Diwan", "0999NoMeta.Work"],
    )
    db_path = tmp_path / "inventory.sqlite"

    report = inventory.build_inventory(
        priority_list_path=priority_list, db_path=db_path, openiti_dir=tmp_path, limit=250
    )
    assert report["works_ingested"] == 3
    assert report["meta_hits"] == 2
    assert report["meta_hit_rate"] == 2 / 3

    stats = inventory.gather_stats(db_path)
    assert stats["works_ingested"] == 3
    assert stats["meta_hits"] == 2
    # resolver coverage measured over the (here, only 3-row) top-200 sample:
    # source_lib_claim resolves for the 2 rows with a versioned url, not the
    # metadata-less third row.
    cov = stats["resolver_coverage_top200"]
    assert cov["sample_size"] == 3
    assert cov["resolved"] == 2
    assert stats["source_lib_distribution"]["Shamela"] == 1
    assert stats["source_lib_distribution"]["JK"] == 1


def test_format_stats_report_contains_generated_on_date():
    stats = {
        "works_ingested": 3,
        "meta_hits": 2,
        "meta_hit_rate": 2 / 3,
        "resolver_coverage_top200": {"sample_size": 3, "resolved": 2, "coverage": 2 / 3},
        "source_lib_distribution": inventory.Counter({"Shamela": 1, "JK": 1, None: 1}),
    }
    report = inventory.format_stats_report(stats, generated_on="2026-08-12")
    assert "Generated on: 2026-08-12" in report
    assert "Shamela" in report
    assert "3" in report
