"""Stub CLI entry points for the versed-translator lab console scripts."""

from __future__ import annotations

import sys

from versed_translator import __version__


def _stub_main(name: str, component: str) -> int:
    if "--version" in sys.argv[1:]:
        print(f"{name} {__version__}")
        return 0
    print(f"{name} {__version__}")
    print(f"not yet implemented — see VERSED_TRANSLATION_ROADMAP.md {component}")
    return 0


def benchmark_main() -> int:
    return _stub_main("versed-benchmark", "C1")


def harness_main() -> int:
    return _stub_main("versed-harness", "C2")


def corpus_main() -> int:
    return _stub_main("versed-corpus", "C6")


if __name__ == "__main__":
    sys.exit(benchmark_main())
