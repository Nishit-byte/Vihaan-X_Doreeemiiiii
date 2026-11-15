"""Developer CLI for VivaVoce M2: Repo, PDF, Challenge, Sandbox Leak, and Replay status.

Usage (from backend/):
    python -m ingestion.dev_cli repo <url|demo>
    python -m ingestion.dev_cli pdf <path>
    python -m ingestion.dev_cli challenge [demo]
    python -m ingestion.dev_cli sandbox-leak
    python -m ingestion.dev_cli replay-status
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

from .config import DEMO_REPO_URL
from .demo_loader import (
    is_demo_source,
    load_demo_challenge,
    load_demo_repo,
    materialize_demo_repo,
)
from .git_blame import compute_authorship_stats, extract_author_map
from .models import IngestionError
from .pdf_parser import parse_research_paper
from .repo_parser import (
    cleanup_repo,
    clone_and_index_repo,
    validate_github_url,
)
try:
    from ..replay.store import ReplayStore
except ImportError:
    from replay.store import ReplayStore

try:
    from ..sandbox.sandbox_runner import execute_verification
except ImportError:
    from sandbox.sandbox_runner import execute_verification


def run_repo(target: str) -> int:
    """Index demo or GitHub repository and print summary."""
    print("=" * 80)
    print(f"REPO INDEXING: {target}")
    print("=" * 80)

    try:
        if is_demo_source(target):
            t0 = time.perf_counter()
            index = clone_and_index_repo("demo", use_cache=True)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            _, _, author_stats = load_demo_repo()
        else:
            validate_github_url(target)
            t0 = time.perf_counter()
            index = clone_and_index_repo(target, use_cache=False)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            files_to_blame = [f.path for f in index.files]
            try:
                extract_author_map(index.local_path, files_to_blame, index=index)
                author_stats = compute_authorship_stats(index.local_path, files_to_blame)
            finally:
                if index.local_path:
                    cleanup_repo(index.local_path)

        print(f"Repo ID:       {index.repo_id}")
        print(f"Source URL:    {index.source_url}")
        print(f"Commit SHA:    {index.commit_sha or '(none)'}")
        print(f"Indexed Files: {len(index.files)} (total .py files: {index.total_py_files})")
        print(f"Truncated:     {index.truncated}")
        print(f"From Cache:    {index.from_cache}")
        print(f"Elapsed Time:  {elapsed_ms:.2f} ms")
        print()

        print(f"Top Ranked Files ({len(index.files)}):")
        for i, f in enumerate(index.files, 1):
            print(
                f"  {i:2d}. {f.path:<32} | {f.line_count:4d} lines | "
                f"{f.import_count:2d} imports | {len(f.functions):2d} funcs | {len(f.classes):2d} classes"
            )
        print()

        print(f"Authorship Breakdown ({len(author_stats)} authors):")
        for stat in author_stats:
            pct = stat.share_of_lines * 100
            print(f"  - {stat.author:<18} <{stat.email}>: {pct:5.1f}% ({stat.lines} lines)")
        print()

        identifiers = index.identifiers(limit=30)
        print(f"Top Identifiers ({len(identifiers)}):")
        print("  " + ", ".join(identifiers))
        print("=" * 80)
        return 0

    except IngestionError as e:
        print(f"INGESTION ERROR: {e}")
        if e.detail:
            print(f"Detail: {e.detail}")
        print("=" * 80)
        return 1
    except Exception as e:
        print(f"UNEXPECTED ERROR: {e}")
        print("=" * 80)
        return 1


def run_pdf(pdf_path_str: str) -> int:
    """Parse research paper PDF and print structured breakdown and Mermaid graph."""
    print("=" * 80)
    print(f"PDF PARSING: {pdf_path_str}")
    print("=" * 80)

    pdf_path = Path(pdf_path_str)
    if not pdf_path.exists():
        print(f"ERROR: File not found: {pdf_path}")
        print("=" * 80)
        return 1

    try:
        pdf_bytes = pdf_path.read_bytes()
        t0 = time.perf_counter()
        index = parse_research_paper(pdf_bytes, use_cache=True)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        print(f"Title:         {index.title}")
        print(f"Page Count:    {index.page_count}")
        print(f"Source:        {index.source}")
        print(f"Paper ID:      {index.paper_id}")
        print(f"Elapsed Time:  {elapsed_ms:.2f} ms")
        print()

        print(f"Sections ({len(index.sections)}):")
        for i, sec in enumerate(index.sections, 1):
            print(f"  {i:2d}. {sec.title} (pages {sec.page_start}–{sec.page_end}, {len(sec.text)} chars)")
        print()

        print(f"Concept Nodes ({len(index.nodes)}):")
        for node in index.nodes:
            status = "VERIFIED" if node.excerpt_verified else "SNAPPED"
            print(f"  - [{node.id}] {node.label} ({status})")
            print(f"      Section:  {node.section} (page {node.page})")
            short_excerpt = node.excerpt.strip().replace("\n", " ")
            if len(short_excerpt) > 90:
                short_excerpt = short_excerpt[:87] + "..."
            print(f"      Excerpt:  \"{short_excerpt}\"")
        print()

        print("Mermaid Diagram:")
        print("-" * 80)
        print(index.mermaid.strip())
        print("=" * 80)
        return 0

    except IngestionError as e:
        print(f"INGESTION ERROR: {e}")
        if e.detail:
            print(f"Detail: {e.detail}")
        print("=" * 80)
        return 1
    except Exception as e:
        print(f"UNEXPECTED ERROR: {e}")
        print("=" * 80)
        return 1


def run_challenge(target: str = "demo") -> int:
    """Run real sandbox verification on the demo challenge starter and reference code."""
    print("=" * 80)
    print(f"CODING CHALLENGE RUN: {target}")
    print("=" * 80)

    if not is_demo_source(target) and target.lower() != "demo":
        print(f"ERROR: Unsupported challenge target '{target}'. Currently only 'demo' is supported.")
        print("=" * 80)
        return 1

    try:
        challenge = load_demo_challenge()
        repo_root = materialize_demo_repo()

        target_file = challenge.get("target_file", "similarity.py")
        function_name = challenge.get("function", "cosine_similarity")
        starter_code = challenge.get("starter_code", "")
        test_code = challenge.get("test_code", "")
        ref_code = challenge.get("reference_solution", "")

        print(f"Challenge Target: {target_file} -> {function_name}()")
        print(f"Description:      {challenge.get('description', '')}")
        print(f"Repo Root:        {repo_root}")
        print()

        # 1. Run starter code (must FAIL)
        print("1. Running STARTER CODE (planted bug, expected to FAIL)...")
        res_starter = execute_verification(target_file, starter_code, test_code, repo_root=repo_root)
        starter_passed = res_starter.passed
        print(f"   Passed:       {res_starter.passed} (Expected: False)")
        print(f"   Tests Passed: {res_starter.tests_passed}")
        print(f"   Tests Failed: {res_starter.tests_failed}")
        print(f"   Runtime:      {res_starter.runtime_ms} ms")
        print(f"   Timed Out:    {res_starter.timed_out}")
        if res_starter.stdout:
            last_lines = [line for line in res_starter.stdout.strip().splitlines() if line.strip()]
            summary_snippet = " | ".join(last_lines[-2:]) if last_lines else ""
            print(f"   Output Tail:  {summary_snippet}")
        print()

        # 2. Run reference solution (must PASS)
        print("2. Running REFERENCE SOLUTION (bug fix, expected to PASS)...")
        res_ref = execute_verification(target_file, ref_code, test_code, repo_root=repo_root)
        ref_passed = res_ref.passed
        print(f"   Passed:       {res_ref.passed} (Expected: True)")
        print(f"   Tests Passed: {res_ref.tests_passed}")
        print(f"   Tests Failed: {res_ref.tests_failed}")
        print(f"   Runtime:      {res_ref.runtime_ms} ms")
        print(f"   Timed Out:    {res_ref.timed_out}")
        if res_ref.stdout:
            last_lines = [line for line in res_ref.stdout.strip().splitlines() if line.strip()]
            summary_snippet = " | ".join(last_lines[-2:]) if last_lines else ""
            print(f"   Output Tail:  {summary_snippet}")
        print()

        starter_ok = (not starter_passed) and (res_starter.tests_failed > 0)
        ref_ok = ref_passed and (res_ref.tests_failed == 0)

        print("Verification Results:")
        print(f"  - Starter code failed as expected:       {starter_ok}")
        print(f"  - Reference solution passed as expected: {ref_ok}")

        if starter_ok and ref_ok:
            print("VERDICT: PASS — Sandbox execution behaves deterministically on demo challenge.")
            print("=" * 80)
            return 0
        else:
            print("VERDICT: FAIL — Challenge outcome did not match expected criteria.")
            print("=" * 80)
            return 1

    except Exception as e:
        print(f"CHALLENGE EXECUTION ERROR: {e}")
        print("=" * 80)
        return 1


def run_sandbox_leak() -> int:
    """Run credential leak check confirming parent secrets do not leak into child process."""
    print("=" * 80)
    print("SANDBOX CREDENTIAL LEAK CHECK")
    print("=" * 80)

    fake_secrets = {
        "GEMINI_API_KEY": "fake_gemini_key_dev_cli_12345",
        "GROQ_API_KEY": "fake_groq_key_dev_cli_67890",
        "SECRET_TOKEN": "super_secret_token_dev_cli_xyz",
    }
    saved_env = {k: os.environ.get(k) for k in fake_secrets}

    test_code = """
import os

def test_credentials_not_in_child_environment():
    # Verify child environment does not have any of the parent's secret variables
    for key in ["GEMINI_API_KEY", "GROQ_API_KEY", "SECRET_TOKEN"]:
        assert key not in os.environ, f"Secret environment variable {key} leaked!"

    env_dump = " ".join(f"{k}={v}" for k, v in os.environ.items())
    assert "fake_gemini_key_dev_cli_12345" not in env_dump, "GEMINI secret value leaked!"
    assert "fake_groq_key_dev_cli_67890" not in env_dump, "GROQ secret value leaked!"
    assert "super_secret_token_dev_cli_xyz" not in env_dump, "SECRET_TOKEN value leaked!"
"""

    try:
        # Populate parent environment with fake secrets
        for k, v in fake_secrets.items():
            os.environ[k] = v

        print("Set temporary fake secrets in parent os.environ:")
        for k in fake_secrets:
            print(f"  - {k}")
        print("Running execute_verification with env inspection test...")

        res = execute_verification("test_leak.py", "x = 42", test_code)

        print(f"  Sandbox Result Passed: {res.passed}")
        print(f"  Tests Passed:          {res.tests_passed}")
        print(f"  Tests Failed:          {res.tests_failed}")
        print(f"  Runtime:               {res.runtime_ms} ms")

        leaked_values = [
            v for v in fake_secrets.values() if v in res.stdout or v in res.stderr
        ]
        leaked_keys = [
            k for k in fake_secrets.keys() if k in res.stdout or k in res.stderr
        ]

        if not res.passed or leaked_values or leaked_keys:
            print("VERDICT: FAIL — Sandbox environment leaked secrets or failed verification!")
            if leaked_values:
                print(f"  Leaked secret values: {leaked_values}")
            if leaked_keys:
                print(f"  Leaked secret keys:   {leaked_keys}")
            print("=" * 80)
            return 1

        print("VERDICT: PASS — No secrets in the child environment (same-user file reads are NOT blocked; see NOTES §4). Child process runs with minimal sanitized env.")
        print("=" * 80)
        return 0

    except Exception as e:
        print(f"SANDBOX LEAK CHECK ERROR: {e}")
        print("=" * 80)
        return 1

    finally:
        for k, old_val in saved_env.items():
            if old_val is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old_val


def run_replay_status() -> int:
    """Display ReplayStore status formatted as JSON."""
    print("=" * 80)
    print("REPLAY STORE STATUS")
    print("=" * 80)

    try:
        store = ReplayStore()
        status_data = store.status()
        print(json.dumps(status_data, indent=2))
        print("=" * 80)
        return 0
    except Exception as e:
        print(f"ERROR reading replay status: {e}")
        print("=" * 80)
        return 1


def main(argv: Optional[list[str]] = None) -> int:
    """Main CLI entrypoint for ingestion.dev_cli."""
    parser = argparse.ArgumentParser(
        prog="python -m ingestion.dev_cli",
        description="VivaVoce M2 Developer CLI: offline verification and inspection tools.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # 1. repo <url|demo>
    repo_parser = subparsers.add_parser("repo", help="Index a GitHub repository or offline demo cache.")
    repo_parser.add_argument("target", help="Repository URL (e.g. https://github.com/owner/repo) or 'demo'")

    # 2. pdf <path>
    pdf_parser_cmd = subparsers.add_parser("pdf", help="Parse research paper PDF into concept graph and Mermaid.")
    pdf_parser_cmd.add_argument("path", help="Path to PDF file")

    # 3. challenge [demo]
    challenge_parser = subparsers.add_parser("challenge", help="Run coding challenge in real sandbox.")
    challenge_parser.add_argument("target", nargs="?", default="demo", help="Challenge target (default: 'demo')")

    # 4. sandbox-leak
    subparsers.add_parser("sandbox-leak", help="Verify zero secret leakage in child execution environment.")

    # 5. replay-status
    subparsers.add_parser("replay-status", help="Print recorded sessions and queue status from ReplayStore.")

    args = parser.parse_args(argv)

    if args.subcommand == "repo":
        return run_repo(args.target)
    elif args.subcommand == "pdf":
        return run_pdf(args.path)
    elif args.subcommand == "challenge":
        return run_challenge(args.target)
    elif args.subcommand == "sandbox-leak":
        return run_sandbox_leak()
    elif args.subcommand == "replay-status":
        return run_replay_status()
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
