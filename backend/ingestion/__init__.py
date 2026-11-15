"""Ingestion package for VivaVoce M2: Repo intelligence, AST indexing, git blame, and PDF parsing."""

from .demo_loader import (
    is_demo_source,
    load_demo_challenge,
    load_demo_repo,
    materialize_demo_repo,
)
from .git_blame import (
    compute_authorship_stats,
    extract_author_map,
    list_authors,
)
from .models import (
    IngestionError,
    PaperIndex,
    RepoIndex,
)
from .pdf_parser import (
    load_cached_paper,
    load_demo_paper_bytes,
    parse_research_paper,
)
from .repo_parser import (
    clone_and_index_repo,
    index_repo_path,
    load_demo_repo_index,
    validate_github_url,
)

__all__ = [
    "clone_and_index_repo",
    "index_repo_path",
    "load_demo_repo_index",
    "validate_github_url",
    "extract_author_map",
    "compute_authorship_stats",
    "list_authors",
    "parse_research_paper",
    "load_demo_paper_bytes",
    "is_demo_source",
    "load_demo_repo",
    "materialize_demo_repo",
    "load_demo_challenge",
    "load_cached_paper",
    "IngestionError",
    "RepoIndex",
    "PaperIndex",
]
