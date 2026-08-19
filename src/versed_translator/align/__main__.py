"""Build and verify portable Arabic-English alignment bundles."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from versed_translator.align.bundle import verify_bundle, write_bundle
from versed_translator.align.embeddings import (
    DEFAULT_EMBEDDING_MODEL,
    TransformerEmbedder,
)
from versed_translator.align.engine import align_documents, with_metrics
from versed_translator.align.io import load_document, load_gold, load_structural_links
from versed_translator.align.metrics import score_sentence_gold
from versed_translator.align.profiles import load_maqama_pair, load_plain_pair
from versed_translator.align.reader_bridge import (
    build_reader_timeline,
    write_reader_timeline,
)


def _add_common_build_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--gold", type=Path)
    parser.add_argument("--max-cells", type=int, default=2_000_000)
    parser.add_argument(
        "--embedding-model",
        nargs="?",
        const=DEFAULT_EMBEDDING_MODEL,
        help=(
            "enable local multilingual semantic scoring; optionally provide a "
            "Transformers model id or directory"
        ),
    )
    parser.add_argument("--embeddings-local-only", action="store_true")
    parser.add_argument("--embedding-batch-size", type=int, default=16)
    parser.add_argument("--force", action="store_true")


def _embedder(args):
    if not args.embedding_model:
        return None
    return TransformerEmbedder(
        args.embedding_model,
        batch_size=args.embedding_batch_size,
        local_files_only=args.embeddings_local_only,
    )


def _finish(result, args, *, extraction: dict | None = None) -> int:
    if extraction:
        result = replace(
            result,
            diagnostics={**result.diagnostics, "extraction": extraction},
        )
    if args.gold:
        result = with_metrics(result, score_sentence_gold(result, load_gold(args.gold)))
    manifest = write_bundle(result, args.out, force=args.force)
    verified = verify_bundle(args.out)
    print(
        json.dumps(
            {
                "bundle": str(args.out.expanduser().resolve()),
                "bundle_id": manifest["bundle_id"],
                "verified": verified["bundle_id"] == manifest["bundle_id"],
                "counts": manifest["counts"],
                "accuracy": result.metrics,
                "diagnostics": result.diagnostics,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _build_normalized(args) -> int:
    arabic = load_document(args.arabic_document)
    english = load_document(args.english_document)
    links = load_structural_links(args.structural_map) if args.structural_map else None
    result = align_documents(
        arabic,
        english,
        structural_links=links,
        embedder=_embedder(args),
        max_cells=args.max_cells,
    )
    return _finish(result, args)


def _build_maqama(args) -> int:
    arabic, english, links, extraction = load_maqama_pair(
        args.arabic,
        args.english,
        work_id=args.work_id,
    )
    result = align_documents(
        arabic,
        english,
        structural_links=links,
        embedder=_embedder(args),
        max_cells=args.max_cells,
    )
    return _finish(result, args, extraction=extraction)


def _build_text(args) -> int:
    arabic, english, links, extraction = load_plain_pair(
        args.arabic,
        args.english,
        work_id=args.work_id,
    )
    result = align_documents(
        arabic,
        english,
        structural_links=links,
        embedder=_embedder(args),
        max_cells=args.max_cells,
    )
    return _finish(result, args, extraction=extraction)


def _bridge_reader(args) -> int:
    timeline = build_reader_timeline(args.bundle, args.ledger)
    write_reader_timeline(timeline, args.out, force=args.force)
    print(
        json.dumps(
            {
                "timeline": str(args.out.expanduser().resolve()),
                "timeline_id": timeline["timeline_id"],
                "bundle_id": timeline["bundle_id"],
                "diagnostics": timeline["diagnostics"],
                "coverage": timeline["coverage"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    normalized = subparsers.add_parser(
        "build",
        help="align any normalized Arabic/English document pair",
    )
    normalized.add_argument("--arabic-document", type=Path, required=True)
    normalized.add_argument("--english-document", type=Path, required=True)
    normalized.add_argument("--structural-map", type=Path)
    _add_common_build_arguments(normalized)
    normalized.set_defaults(handler=_build_normalized)

    maqama = subparsers.add_parser(
        "build-maqama",
        help="discover and align an OpenITI/English maqama pair",
    )
    maqama.add_argument("--arabic", type=Path, required=True)
    maqama.add_argument("--english", type=Path, required=True)
    maqama.add_argument("--work-id")
    _add_common_build_arguments(maqama)
    maqama.set_defaults(handler=_build_maqama)

    plain = subparsers.add_parser(
        "build-text",
        help="align any OpenITI source with a prepared plain-English translation",
    )
    plain.add_argument("--arabic", type=Path, required=True)
    plain.add_argument("--english", type=Path, required=True)
    plain.add_argument("--work-id")
    _add_common_build_arguments(plain)
    plain.set_defaults(handler=_build_text)

    verify = subparsers.add_parser("verify", help="verify a bundle's manifest")
    verify.add_argument("bundle", type=Path)
    verify.set_defaults(
        handler=lambda args: print(
            json.dumps(verify_bundle(args.bundle), ensure_ascii=False, indent=2)
        )
        or 0
    )

    bridge = subparsers.add_parser(
        "bridge-reader",
        help="compose a verified alignment bundle with an OpenITI audio ledger",
    )
    bridge.add_argument("--bundle", type=Path, required=True)
    bridge.add_argument("--ledger", type=Path, required=True)
    bridge.add_argument("--out", type=Path, required=True)
    bridge.add_argument("--force", action="store_true")
    bridge.set_defaults(handler=_bridge_reader)

    args = parser.parse_args(argv)
    if args.command.startswith("build") and args.max_cells <= 0:
        parser.error("--max-cells must be positive")
    if args.command.startswith("build") and args.embedding_batch_size <= 0:
        parser.error("--embedding-batch-size must be positive")
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
