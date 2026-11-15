"""Tests for TASK S1: scaffold, configuration, models, stubs, and imports."""

import inspect
import logging
import os
import sys
from pathlib import Path

import pytest


def test_packages_importable():
    """Verify that all required virtual environment dependencies are importable."""
    import fastapi
    import fpdf
    import google.genai
    import httpx
    import pydantic
    import pymupdf
    import pytest
    from dotenv import load_dotenv

    assert pymupdf is not None
    assert google.genai is not None
    assert pydantic is not None
    assert fastapi is not None
    assert httpx is not None
    assert pytest is not None
    assert load_dotenv is not None
    assert fpdf is not None


def test_config_clean_import_and_defaults():
    """Verify config.py imports cleanly with all required constants and paths."""
    from ingestion import config

    # Check types and defaults
    assert isinstance(config.GEMINI_API_KEY, str)
    assert config.GEMINI_MODEL == "gemini-2.5-flash"
    assert config.GEMINI_TIMEOUT_S == 30
    assert config.CLONE_TIMEOUT_S == 45
    assert config.CLONE_DEPTH == 50
    assert config.FULL_CLONE_MAX_KB == 20000
    assert config.MAX_INDEXED_FILES == 15
    assert config.MAX_FILE_LINES == 2000
    assert config.MAX_REPO_PY_FILES == 2000
    assert config.SANDBOX_TIMEOUT_S == 8
    assert config.SANDBOX_OUTPUT_LIMIT == 8000
    assert (
        config.DEMO_REPO_URL
        == "https://github.com/shreyas-269/vivavoce-demo-repo"
    )
    assert isinstance(config.DEMO_REPLAY, bool)
    assert isinstance(config.DEMO_RECORD, bool)

    # Check path logic
    backend_path = Path(config.BACKEND_DIR)
    assert backend_path.exists()
    assert (backend_path / "ingestion").exists()

    assert config.DEMO_CACHE_DIR.endswith("demo_cache")
    assert config.REPLAY_DIR.endswith("replay")
    assert "vivavoce" in config.WORK_DIR.lower()

    # Check logger
    assert isinstance(config.log, logging.Logger)
    assert config.log.name == "vivavoce.ingestion"


def test_models_fields_and_methods():
    """Verify all internal Pydantic models in models.py have exact fields and types."""
    from ingestion.models import (
        AuthorStat,
        ConceptEdge,
        ConceptNode,
        ConstantInfo,
        FileIndex,
        FunctionInfo,
        IngestionError,
        OwnedSymbol,
        PaperIndex,
        PaperSection,
        RepoIndex,
        SandboxResult,
    )

    # IngestionError
    err = IngestionError("test message", "detailed reason")
    assert err.user_message == "test message"
    assert err.detail == "detailed reason"
    assert "test message" in str(err)
    assert isinstance(err, Exception)

    # FunctionInfo fields
    fi_fields = FunctionInfo.model_fields.keys()
    for field in [
        "name",
        "qualname",
        "kind",
        "args",
        "docstring",
        "line_start",
        "line_end",
        "calls",
    ]:
        assert field in fi_fields

    # ConstantInfo fields
    ci_fields = ConstantInfo.model_fields.keys()
    for field in ["name", "value_repr", "line"]:
        assert field in ci_fields

    # FileIndex fields
    file_fields = FileIndex.model_fields.keys()
    for field in [
        "path",
        "line_count",
        "import_count",
        "imports",
        "functions",
        "classes",
        "constants",
        "content",
    ]:
        assert field in file_fields

    # RepoIndex fields and stubs
    repo_fields = RepoIndex.model_fields.keys()
    for field in [
        "repo_id",
        "source_url",
        "local_path",
        "commit_sha",
        "files",
        "file_tree",
        "total_py_files",
        "truncated",
        "from_cache",
        "created_at",
    ]:
        assert field in repo_fields

    repo = RepoIndex(repo_id="r1", source_url="https://github.com/foo/bar")
    assert repo.get_file("test.py") is None
    assert repo.identifiers() == []
    assert repo.numbered_source("test.py") == ""
    assert repo.find_function("test.py", 10) is None
    assert repo.snap_range("test.py", 1, 5) == ("test.py", 1, 5)

    # Check signatures on RepoIndex methods
    assert list(inspect.signature(RepoIndex.get_file).parameters.keys()) == [
        "self",
        "path",
    ]
    assert list(inspect.signature(RepoIndex.identifiers).parameters.keys()) == [
        "self",
        "limit",
    ]
    assert list(
        inspect.signature(RepoIndex.numbered_source).parameters.keys()
    ) == ["self", "path", "start", "end"]
    assert list(
        inspect.signature(RepoIndex.find_function).parameters.keys()
    ) == ["self", "path", "line"]
    assert list(inspect.signature(RepoIndex.snap_range).parameters.keys()) == [
        "self",
        "path",
        "start",
        "end",
    ]

    # OwnedSymbol fields
    os_fields = OwnedSymbol.model_fields.keys()
    for field in [
        "file_path",
        "symbol",
        "line_start",
        "line_end",
        "lines_owned",
        "share",
    ]:
        assert field in os_fields

    # AuthorStat fields
    as_fields = AuthorStat.model_fields.keys()
    for field in ["author", "email", "lines", "share_of_lines"]:
        assert field in as_fields

    # PaperSection fields
    ps_fields = PaperSection.model_fields.keys()
    for field in ["title", "page_start", "page_end", "text"]:
        assert field in ps_fields

    # ConceptNode fields
    cn_fields = ConceptNode.model_fields.keys()
    for field in [
        "id",
        "label",
        "excerpt",
        "section",
        "page",
        "excerpt_verified",
    ]:
        assert field in cn_fields

    # ConceptEdge fields
    ce_fields = ConceptEdge.model_fields.keys()
    for field in ["source", "target", "label"]:
        assert field in ce_fields

    # PaperIndex fields
    pi_fields = PaperIndex.model_fields.keys()
    for field in [
        "paper_id",
        "title",
        "page_count",
        "sections",
        "full_text",
        "nodes",
        "edges",
        "mermaid",
        "excerpts",
        "source",
    ]:
        assert field in pi_fields

    # SandboxResult fields
    sr_fields = SandboxResult.model_fields.keys()
    for field in [
        "passed",
        "stdout",
        "stderr",
        "runtime_ms",
        "timed_out",
        "tests_passed",
        "tests_failed",
        "error",
    ]:
        assert field in sr_fields


def test_repo_parser_signatures():
    """Verify repo_parser module signatures match CONTEXT §5.3."""
    import ingestion.repo_parser as mod

    assert list(
        inspect.signature(mod.validate_github_url).parameters.keys()
    ) == ["url"]
    assert list(inspect.signature(mod.clone_repo).parameters.keys()) == [
        "github_url",
        "dest_dir",
    ]
    assert list(inspect.signature(mod.rank_python_files).parameters.keys()) == [
        "repo_path"
    ]
    assert list(inspect.signature(mod.index_repo_path).parameters.keys()) == [
        "repo_path",
        "source_url",
    ]

    sig = inspect.signature(mod.clone_and_index_repo)
    assert list(sig.parameters.keys()) == ["github_url", "use_cache"]
    assert (
        sig.parameters["use_cache"].kind
        == inspect.Parameter.KEYWORD_ONLY
    )
    assert sig.parameters["use_cache"].default is True

    assert list(inspect.signature(mod.cleanup_repo).parameters.keys()) == [
        "path"
    ]


def test_git_blame_signatures():
    """Verify git_blame module signatures match CONTEXT §5.4."""
    import ingestion.git_blame as mod

    assert list(inspect.signature(mod.blame_file).parameters.keys()) == [
        "repo_path",
        "file_path",
    ]
    assert list(
        inspect.signature(mod.normalize_identity).parameters.keys()
    ) == ["name", "email", "alias_map"]
    assert list(inspect.signature(mod.extract_author_map).parameters.keys()) == [
        "repo_path",
        "files",
        "index",
        "alias_map",
    ]
    assert list(
        inspect.signature(mod.compute_authorship_stats).parameters.keys()
    ) == ["repo_path", "files", "alias_map"]
    assert list(inspect.signature(mod.list_authors).parameters.keys()) == [
        "author_map"
    ]


def test_demo_loader_signatures():
    """Verify demo_loader module signatures match CONTEXT §5.5."""
    import ingestion.demo_loader as mod

    assert list(inspect.signature(mod.is_demo_source).parameters.keys()) == [
        "url_or_name"
    ]
    assert (
        list(inspect.signature(mod.load_demo_repo).parameters.keys()) == []
    )
    assert (
        list(inspect.signature(mod.materialize_demo_repo).parameters.keys())
        == []
    )
    assert (
        list(inspect.signature(mod.load_demo_challenge).parameters.keys()) == []
    )


def test_pdf_parser_signatures():
    """Verify pdf_parser module signatures match CONTEXT §5.6."""
    import ingestion.pdf_parser as mod

    assert list(inspect.signature(mod.extract_sections).parameters.keys()) == [
        "pdf_bytes"
    ]
    assert list(
        inspect.signature(mod.build_concept_graph).parameters.keys()
    ) == ["full_text", "sections"]
    assert list(inspect.signature(mod.build_mermaid).parameters.keys()) == [
        "nodes",
        "edges",
    ]
    assert list(inspect.signature(mod.verify_excerpt).parameters.keys()) == [
        "excerpt",
        "full_text",
    ]
    assert list(inspect.signature(mod.load_cached_paper).parameters.keys()) == [
        "pdf_bytes"
    ]
    assert list(inspect.signature(mod.save_cached_paper).parameters.keys()) == [
        "index"
    ]

    sig = inspect.signature(mod.parse_research_paper)
    assert list(sig.parameters.keys()) == ["pdf_bytes", "use_gemini", "use_cache"]
    assert (
        sig.parameters["use_gemini"].kind
        == inspect.Parameter.KEYWORD_ONLY
    )
    assert (
        sig.parameters["use_cache"].kind
        == inspect.Parameter.KEYWORD_ONLY
    )


def test_sandbox_signatures():
    """Verify sandbox_runner module signatures match CONTEXT §5.7."""
    import sandbox.sandbox_runner as mod

    sig_sync = inspect.signature(mod.execute_verification)
    assert list(sig_sync.parameters.keys()) == [
        "file_path",
        "student_code",
        "test_code",
        "repo_root",
    ]
    assert sig_sync.parameters["repo_root"].default is None

    sig_async = inspect.signature(mod.execute_verification_async)
    assert list(sig_async.parameters.keys()) == [
        "file_path",
        "student_code",
        "test_code",
        "repo_root",
    ]
    assert inspect.iscoroutinefunction(mod.execute_verification_async)

    assert (
        list(inspect.signature(mod.warm_up_sandbox).parameters.keys()) == []
    )


def test_replay_signatures():
    """Verify replay package modules match CONTEXT §5.8."""
    from replay.middleware import ReplayMiddleware
    from replay.store import ReplayStore
    import replay

    # Store signatures
    assert list(
        inspect.signature(ReplayStore.__init__).parameters.keys()
    ) == ["self", "replay_dir"]
    assert list(inspect.signature(ReplayStore.record).parameters.keys()) == [
        "self",
        "method",
        "path",
        "status",
        "body",
    ]
    assert list(inspect.signature(ReplayStore.next).parameters.keys()) == [
        "self",
        "method",
        "path",
    ]
    assert list(inspect.signature(ReplayStore.reset).parameters.keys()) == [
        "self"
    ]
    assert list(inspect.signature(ReplayStore.status).parameters.keys()) == [
        "self"
    ]
    assert list(inspect.signature(ReplayStore.clear).parameters.keys()) == [
        "self"
    ]
    assert list(
        inspect.signature(ReplayStore.normalize_path).parameters.keys()
    ) == ["self", "path"]

    # Middleware
    assert list(
        inspect.signature(ReplayMiddleware.__init__).parameters.keys()
    ) == ["self", "app"]
    assert list(
        inspect.signature(ReplayMiddleware.__call__).parameters.keys()
    ) == ["self", "scope", "receive", "send"]

    # Package exports
    assert hasattr(replay, "ReplayStore")
    assert hasattr(replay, "ReplayMiddleware")
    assert hasattr(replay, "is_replay_enabled")
    assert hasattr(replay, "is_record_enabled")
    assert callable(replay.is_replay_enabled)
    assert callable(replay.is_record_enabled)


def test_package_reexports():
    """Verify package __init__.py re-exports match CONTEXT §5.10."""
    import ingestion
    import sandbox

    expected_ingestion_exports = [
        "clone_and_index_repo",
        "index_repo_path",
        "validate_github_url",
        "extract_author_map",
        "compute_authorship_stats",
        "list_authors",
        "parse_research_paper",
        "is_demo_source",
        "load_demo_repo",
        "materialize_demo_repo",
        "load_demo_challenge",
        "load_cached_paper",
        "IngestionError",
        "RepoIndex",
        "PaperIndex",
    ]
    for name in expected_ingestion_exports:
        assert hasattr(ingestion, name), f"Missing ingestion export: {name}"

    expected_sandbox_exports = [
        "execute_verification",
        "execute_verification_async",
        "warm_up_sandbox",
        "SandboxResult",
    ]
    for name in expected_sandbox_exports:
        assert hasattr(sandbox, name), f"Missing sandbox export: {name}"


@pytest.mark.network
def test_network_marker_execution():
    """Will only execute if M2_NETWORK_TESTS=1."""
    assert os.getenv("M2_NETWORK_TESTS") == "1"


@pytest.mark.gemini
def test_gemini_marker_execution():
    """Will only execute if GEMINI_API_KEY is non-empty."""
    assert bool(os.getenv("GEMINI_API_KEY", "").strip())
