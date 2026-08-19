"""Smoke tests: imports, console script entry points, and paths.py defaults/overrides."""

from __future__ import annotations

import importlib

import pytest

SUBPACKAGES = ["benchmark", "harness", "qe", "align", "corpus", "throughput", "factory"]


@pytest.mark.parametrize("name", SUBPACKAGES)
def test_subpackage_imports(name):
    mod = importlib.import_module(f"versed_translator.{name}")
    assert mod.__doc__


def test_top_level_import_and_version():
    import versed_translator

    assert versed_translator.__version__ == "0.0.1"


def test_cli_entry_functions_run(capsys, monkeypatch):
    import sys

    from versed_translator import cli

    monkeypatch.setattr(sys, "argv", ["prog"])
    for fn in (cli.benchmark_main, cli.harness_main):
        rc = fn()
        assert rc == 0
        captured = capsys.readouterr()
        assert "not yet implemented" in captured.out

    monkeypatch.setattr(sys, "argv", ["versed-corpus", "--version"])
    rc = cli.corpus_main()
    assert rc == 0
    assert "versed-corpus" in capsys.readouterr().out


def test_paths_defaults(monkeypatch):
    monkeypatch.delenv("VERSED_DATA", raising=False)
    monkeypatch.delenv("VERSED_SCRATCH", raising=False)
    monkeypatch.delenv("VERSED_SHARED", raising=False)
    monkeypatch.delenv("VERSED_OPENITI", raising=False)
    importlib.reload(importlib.import_module("versed_translator.paths"))
    from versed_translator import paths

    importlib.reload(paths)

    assert paths.PACKAGE_DIR.name == "versed_translator"
    assert paths.REPO_DIR.name == "versed_translator"
    assert paths.DATA_DIR.name == "versed-translator-data"
    assert str(paths.SCRATCH_DIR) == "/Volumes/Nodes/versed-translator"
    assert str(paths.SHARED_DIR) == "/Volumes/hikma/versed-translator"
    assert str(paths.OPENITI_DIR) == "/Volumes/hikma/OpenITI"


def test_paths_env_overrides(monkeypatch, tmp_path):
    scratch = tmp_path / "scratch"
    shared = tmp_path / "shared"
    openiti = tmp_path / "openiti"
    data = tmp_path / "data"
    monkeypatch.setenv("VERSED_DATA", str(data))
    monkeypatch.setenv("VERSED_SCRATCH", str(scratch))
    monkeypatch.setenv("VERSED_SHARED", str(shared))
    monkeypatch.setenv("VERSED_OPENITI", str(openiti))

    from versed_translator import paths

    importlib.reload(paths)
    try:
        assert str(paths.DATA_DIR) == str(data)
        assert str(paths.SCRATCH_DIR) == str(scratch)
        assert str(paths.SHARED_DIR) == str(shared)
        assert str(paths.OPENITI_DIR) == str(openiti)

        assert not scratch.exists()
        assert not shared.exists()

        paths.ensure_dirs()
        assert scratch.is_dir()
        assert shared.is_dir()
        assert not openiti.exists()
    finally:
        importlib.reload(paths)
