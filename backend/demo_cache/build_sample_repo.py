"""Deterministic build script for the 'studysync' demo repository.

Creates:
1. sample_repo.bundle (git bundle with 12-15 commits by Aman, Priya, Rohan)
2. sample_repo_index.json (RepoIndex metadata, local_path blanked, source_url = DEMO_REPO_URL)
3. sample_repo_authors.json (author map + authorship statistics)
4. sample_repo_challenge.json (coding challenge with starter code, test code, reference solution)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

# Ensure backend root is on sys.path
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from ingestion.config import DEMO_CACHE_DIR, DEMO_REPO_URL
from ingestion.git_blame import compute_authorship_stats, extract_author_map
from ingestion.models import AuthorStat, OwnedSymbol, RepoIndex
from ingestion.repo_parser import cleanup_repo, index_repo_path


# Fictional authors
AUTHORS = {
    "aman": {"name": "Aman Verma", "email": "aman@example.com"},
    "priya": {"name": "Priya Nair", "email": "priya@example.com"},
    "rohan": {"name": "Rohan Gupta", "email": "rohan@example.com"},
}

# Source code for the studysync modules

UTILS_INIT_CONTENT = '''"""Vector and math operations utility package for studysync."""

from utils.vector_ops import dot_product, normalize_vector, vector_norm

__all__ = ["dot_product", "vector_norm", "normalize_vector"]
'''

UTILS_VECTOR_OPS_BASE = '''"""Vector math utilities for computing distances and norms."""

import math


def dot_product(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute dot product of two numeric vectors of identical length."""
    if len(vec_a) != len(vec_b):
        raise ValueError("Vectors must have the same dimension")
    return sum(a * b for a, b in zip(vec_a, vec_b))


def vector_norm(vec: list[float]) -> float:
    """Compute Euclidean L2 norm of a vector."""
    return math.sqrt(sum(x * x for x in vec))
'''

UTILS_VECTOR_OPS_FULL = '''"""Vector math utilities for computing distances and norms."""

import math


def dot_product(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute dot product of two numeric vectors of identical length."""
    if len(vec_a) != len(vec_b):
        raise ValueError("Vectors must have the same dimension")
    return sum(a * b for a, b in zip(vec_a, vec_b))


def vector_norm(vec: list[float]) -> float:
    """Compute Euclidean L2 norm of a vector."""
    return math.sqrt(sum(x * x for x in vec))


def normalize_vector(vec: list[float]) -> list[float]:
    """Normalize vector to unit length, returning zeroes if norm is 0."""
    norm = vector_norm(vec)
    if norm == 0.0:
        return [0.0] * len(vec)
    return [x / norm for x in vec]
'''

MODELS_BASE = '''"""Student and study group domain models for studysync."""

from dataclasses import dataclass, field


@dataclass
class Student:
    """Student profile representation for peer matching."""

    student_id: int
    name: str
    skills: list[str] = field(default_factory=list)
    interests: list[str] = field(default_factory=list)
    skill_vector: list[float] = field(default_factory=list)
    target_hours: float = 10.0

    def has_common_interest(self, other: "Student") -> bool:
        """Check if this student shares any interest with another student."""
        return bool(set(self.interests) & set(other.interests))
'''

MODELS_FULL = '''"""Student and study group domain models for studysync."""

from dataclasses import dataclass, field


@dataclass
class Student:
    """Student profile representation for peer matching."""

    student_id: int
    name: str
    skills: list[str] = field(default_factory=list)
    interests: list[str] = field(default_factory=list)
    skill_vector: list[float] = field(default_factory=list)
    target_hours: float = 10.0

    def has_common_interest(self, other: "Student") -> bool:
        """Check if this student shares any interest with another student."""
        return bool(set(self.interests) & set(other.interests))

    def profile_summary(self) -> str:
        """Return human-readable summary of student profile."""
        skill_str = ", ".join(self.skills) or "none"
        interest_str = ", ".join(self.interests) or "general"
        return (
            f"{self.name} (ID: {self.student_id}) | "
            f"Skills: [{skill_str}] | Interests: [{interest_str}]"
        )


def create_student(
    student_id: int,
    name: str,
    skills: list[str],
    interests: list[str],
    skill_vector: list[float],
    target_hours: float = 10.0,
) -> Student:
    """Factory function to instantiate a validated Student object."""
    return Student(
        student_id=student_id,
        name=name,
        skills=list(skills),
        interests=list(interests),
        skill_vector=list(skill_vector),
        target_hours=target_hours,
    )


def is_suitable_partner(
    student: Student, candidate: Student, min_common_skills: int = 1
) -> bool:
    """Determine if candidate meets baseline skill and interest compatibility."""
    if student.student_id == candidate.student_id:
        return False
    common = set(student.skills) & set(candidate.skills)
    return len(common) >= min_common_skills
'''

SIMILARITY_COSINE_ONLY = '''"""Similarity metrics for comparing student skills and shared interests."""

from utils.vector_ops import dot_product, vector_norm


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two numeric vectors.

    Uses dot product and Euclidean norm from utils.vector_ops.
    Returns a score between -1.0 and 1.0.
    """
    if len(vec_a) != len(vec_b):
        raise ValueError("Vectors must have the same dimension")
    dot = dot_product(vec_a, vec_b)
    norm_a = vector_norm(vec_a)
    norm_b = vector_norm(vec_b)
    return dot / (norm_a * norm_b)
'''

SIMILARITY_WITH_JACCARD = '''"""Similarity metrics for comparing student skills and shared interests."""

from utils.vector_ops import dot_product, vector_norm


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two numeric vectors.

    Uses dot product and Euclidean norm from utils.vector_ops.
    Returns a score between -1.0 and 1.0.
    """
    if len(vec_a) != len(vec_b):
        raise ValueError("Vectors must have the same dimension")
    dot = dot_product(vec_a, vec_b)
    norm_a = vector_norm(vec_a)
    norm_b = vector_norm(vec_b)
    return dot / (norm_a * norm_b)


def jaccard_similarity(
    set_a: list[str] | set[str], set_b: list[str] | set[str]
) -> float:
    """Compute Jaccard similarity coefficient between two sets of items."""
    s_a = set(set_a)
    s_b = set(set_b)
    union_len = len(s_a | s_b)
    if union_len == 0:
        return 0.0
    return len(s_a & s_b) / union_len
'''

SIMILARITY_BUGGY = '''"""Similarity metrics for comparing student skills and shared interests."""

from utils.vector_ops import dot_product, vector_norm


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two numeric vectors.

    Uses dot product and Euclidean norm from utils.vector_ops.
    Returns a score between -1.0 and 1.0.
    """
    if len(vec_a) != len(vec_b):
        raise ValueError("Vectors must have the same dimension")
    dot = dot_product(vec_a, vec_b)
    norm_a = vector_norm(vec_a)
    norm_b = vector_norm(vec_b)
    return dot / (norm_a * norm_b)


def jaccard_similarity(
    set_a: list[str] | set[str], set_b: list[str] | set[str]
) -> float:
    """Compute Jaccard similarity coefficient between two sets of items."""
    s_a = set(set_a)
    s_b = set(set_b)
    union_len = len(s_a | s_b)
    if union_len == 0:
        return 0.0
    return len(s_a & s_b) / union_len


def composite_similarity(
    student_a_vec: list[float],
    student_b_vec: list[float],
    interests_a: list[str],
    interests_b: list[str],
    skill_weight: float = 0.7,
) -> float:
    """Calculate weighted composite similarity across skills and interests."""
    cos_sim = cosine_similarity(student_a_vec, student_b_vec)
    jac_sim = jaccard_similarity(interests_a, interests_b)
    interest_weight = 1.0 - skill_weight
    return (skill_weight * cos_sim) + (interest_weight * jac_sim)
'''

SIMILARITY_FIXED = '''"""Similarity metrics for comparing student skills and shared interests."""

from utils.vector_ops import dot_product, vector_norm


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two numeric vectors.

    Uses dot product and Euclidean norm from utils.vector_ops.
    Returns a score between -1.0 and 1.0.
    """
    if len(vec_a) != len(vec_b):
        raise ValueError("Vectors must have the same dimension")
    dot = dot_product(vec_a, vec_b)
    norm_a = vector_norm(vec_a)
    norm_b = vector_norm(vec_b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def jaccard_similarity(
    set_a: list[str] | set[str], set_b: list[str] | set[str]
) -> float:
    """Compute Jaccard similarity coefficient between two sets of items."""
    s_a = set(set_a)
    s_b = set(set_b)
    union_len = len(s_a | s_b)
    if union_len == 0:
        return 0.0
    return len(s_a & s_b) / union_len


def composite_similarity(
    student_a_vec: list[float],
    student_b_vec: list[float],
    interests_a: list[str],
    interests_b: list[str],
    skill_weight: float = 0.7,
) -> float:
    """Calculate weighted composite similarity across skills and interests."""
    cos_sim = cosine_similarity(student_a_vec, student_b_vec)
    jac_sim = jaccard_similarity(interests_a, interests_b)
    interest_weight = 1.0 - skill_weight
    return (skill_weight * cos_sim) + (interest_weight * jac_sim)
'''

DATA_LOADER_BASE = '''"""Dataset loader utilities for studysync demo."""

from models import Student, create_student


def parse_student_record(record: dict) -> Student:
    """Parse dictionary record into a validated Student instance."""
    return create_student(
        student_id=int(record["student_id"]),
        name=str(record["name"]),
        skills=list(record.get("skills", [])),
        interests=list(record.get("interests", [])),
        skill_vector=[float(x) for x in record.get("skill_vector", [])],
        target_hours=float(record.get("target_hours", 10.0)),
    )
'''

DATA_LOADER_FULL = '''"""Dataset loader utilities for studysync demo."""

from models import Student, create_student


def parse_student_record(record: dict) -> Student:
    """Parse dictionary record into a validated Student instance."""
    return create_student(
        student_id=int(record["student_id"]),
        name=str(record["name"]),
        skills=list(record.get("skills", [])),
        interests=list(record.get("interests", [])),
        skill_vector=[float(x) for x in record.get("skill_vector", [])],
        target_hours=float(record.get("target_hours", 10.0)),
    )


def load_sample_students() -> list[Student]:
    """Provide sample cohort of students for testing."""
    c1 = {
        "student_id": 1,
        "name": "Aarav Sharma",
        "skills": ["python", "ai"],
        "interests": ["robotics"],
        "skill_vector": [1.0, 0.8, 0.2, 0.0],
    }
    c2 = {
        "student_id": 2,
        "name": "Bhavna Patel",
        "skills": ["python", "data"],
        "interests": ["algorithms"],
        "skill_vector": [0.9, 0.7, 0.4, 0.1],
    }
    return [parse_student_record(c1), parse_student_record(c2)]
'''

RANKING_CORE = '''"""Candidate ranking and matching algorithms for study partners."""

from models import Student
from similarity import composite_similarity


def score_student_pair(
    student: Student, candidate: Student, skill_weight: float = 0.7
) -> float:
    """Compute overall compatibility score between two students."""
    return composite_similarity(
        student.skill_vector,
        candidate.skill_vector,
        student.interests,
        candidate.interests,
        skill_weight=skill_weight,
    )


def top_k_partners(
    target: Student,
    candidates: list[Student],
    k: int = 3,
    min_score: float = 0.0,
) -> list[tuple[Student, float]]:
    """Return top-k highest scoring study partner candidates for a student."""
    scored: list[tuple[Student, float]] = []
    for cand in candidates:
        if cand.student_id == target.student_id:
            continue
        score = score_student_pair(target, cand)
        if score >= min_score:
            scored.append((cand, score))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:k]


def filter_by_min_score(
    scored_pairs: list[tuple[Student, float]], threshold: float = 0.5
) -> list[tuple[Student, float]]:
    """Filter candidate matches by minimum threshold score."""
    return [pair for pair in scored_pairs if pair[1] >= threshold]


def explain_match_score(
    student: Student, candidate: Student
) -> str:
    """Return concise description of matching factors for pairs."""
    return f"Match between {student.name} and {candidate.name}"
'''

RANKING_FULL = '''"""Candidate ranking and matching algorithms for study partners."""

from models import Student
from similarity import composite_similarity


def score_student_pair(
    student: Student, candidate: Student, skill_weight: float = 0.7
) -> float:
    """Compute overall compatibility score between two students."""
    return composite_similarity(
        student.skill_vector,
        candidate.skill_vector,
        student.interests,
        candidate.interests,
        skill_weight=skill_weight,
    )


def top_k_partners(
    target: Student,
    candidates: list[Student],
    k: int = 3,
    min_score: float = 0.0,
) -> list[tuple[Student, float]]:
    """Return top-k highest scoring study partner candidates for a student."""
    scored: list[tuple[Student, float]] = []
    for cand in candidates:
        if cand.student_id == target.student_id:
            continue
        score = score_student_pair(target, cand)
        if score >= min_score:
            scored.append((cand, score))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:k]


def filter_by_min_score(
    scored_pairs: list[tuple[Student, float]], threshold: float = 0.5
) -> list[tuple[Student, float]]:
    """Filter candidate matches by minimum threshold score."""
    return [pair for pair in scored_pairs if pair[1] >= threshold]


def explain_match_score(
    student: Student, candidate: Student
) -> str:
    """Return concise description of matching factors for pairs."""
    return f"Match between {student.name} and {candidate.name}"


def find_mutual_partners(
    students: list[Student], k: int = 2
) -> dict[int, list[int]]:
    """Find mutual top-k partner matches across an entire student cohort."""
    recommendations: dict[int, list[int]] = {}
    for st in students:
        ranked = top_k_partners(st, students, k=k)
        recommendations[st.student_id] = [c.student_id for c, _ in ranked]

    mutual_matches: dict[int, list[int]] = {st.student_id: [] for st in students}
    for sid, recs in recommendations.items():
        for other_id in recs:
            if sid in recommendations.get(other_id, []):
                if other_id not in mutual_matches[sid]:
                    mutual_matches[sid].append(other_id)

    return mutual_matches


def reciprocal_match_score(
    rankings_a: list[int], sid_b: int, rankings_b: list[int], sid_a: int
) -> float:
    """Calculate reciprocal ranking score between two students."""
    r_a = rankings_a.index(sid_b) + 1 if sid_b in rankings_a else 100
    r_b = rankings_b.index(sid_a) + 1 if sid_a in rankings_b else 100
    return 1.0 / (r_a + r_b)


def harmonic_rank_score(rank_a: int, rank_b: int) -> float:
    """Compute harmonic mean of bilateral partner ranks."""
    if rank_a <= 0 or rank_b <= 0:
        return 0.0
    return 2.0 / ((1.0 / rank_a) + (1.0 / rank_b))
'''

CLI_CONTENT = '''"""Command-line interface demo entrypoint for studysync."""

from data_loader import load_sample_students
from models import Student
from ranking import top_k_partners


def format_recommendations(
    target: Student, matches: list[tuple[Student, float]]
) -> str:
    """Format matching recommendations into a summary table."""
    lines = [f"Top Study Partners for {target.name}:"]
    for rank, (cand, score) in enumerate(matches, start=1):
        lines.append(f"  {rank}. {cand.name} (Score: {score:.3f})")
    return "\\n".join(lines)


def main() -> int:
    """Run CLI demo for default cohort."""
    cohort = load_sample_students()
    if cohort:
        recs = top_k_partners(cohort[0], cohort, k=2)
        print(format_recommendations(cohort[0], recs))
    return 0
'''

CHALLENGE_TEST_CODE = '''"""Unit tests for similarity metrics in studysync."""

import pytest
from similarity import cosine_similarity


def test_cosine_similarity_identical_vectors():
    """Identical non-zero vectors should have similarity 1.0."""
    v1 = [1.0, 2.0, 3.0]
    v2 = [1.0, 2.0, 3.0]
    assert cosine_similarity(v1, v2) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors():
    """Orthogonal vectors should have similarity 0.0."""
    v1 = [1.0, 0.0]
    v2 = [0.0, 1.0]
    assert cosine_similarity(v1, v2) == pytest.approx(0.0)


def test_cosine_similarity_scaled_vectors():
    """Vectors in identical direction with different norms have similarity 1.0."""
    v1 = [1.0, 2.0]
    v2 = [2.0, 4.0]
    assert cosine_similarity(v1, v2) == pytest.approx(1.0)


def test_cosine_similarity_zero_vector_edge_case():
    """All-zero vector should return 0.0 without raising ZeroDivisionError."""
    v1 = [0.0, 0.0, 0.0]
    v2 = [1.0, 2.0, 3.0]
    assert cosine_similarity(v1, v2) == pytest.approx(0.0)


def test_cosine_similarity_both_zero_vectors():
    """Two all-zero vectors should return 0.0 without raising ZeroDivisionError."""
    v1 = [0.0, 0.0]
    v2 = [0.0, 0.0]
    assert cosine_similarity(v1, v2) == pytest.approx(0.0)


def test_cosine_similarity_dimension_mismatch():
    """Vectors of different dimensions should raise ValueError."""
    v1 = [1.0, 2.0]
    v2 = [1.0, 2.0, 3.0]
    with pytest.raises(ValueError):
        cosine_similarity(v1, v2)
'''


def _commit_step(
    repo_dir: Path,
    author_key: str,
    date_str: str,
    message: str,
) -> None:
    """Create a deterministic git commit with fixed author and timestamp."""
    author = AUTHORS[author_key]
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = author["name"]
    env["GIT_AUTHOR_EMAIL"] = author["email"]
    env["GIT_AUTHOR_DATE"] = date_str
    env["GIT_COMMITTER_NAME"] = author["name"]
    env["GIT_COMMITTER_EMAIL"] = author["email"]
    env["GIT_COMMITTER_DATE"] = date_str
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    env["GIT_ASKPASS"] = "echo"

    subprocess.run(["git", "add", "-A"], cwd=repo_dir, env=env, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo_dir, env=env, check=True)


def build_sample_repo(output_dir: Optional[str] = None) -> dict[str, str]:
    """Build the deterministic sample_repo git bundle and metadata JSON files.

    Outputs:
    - sample_repo.bundle
    - sample_repo_index.json
    - sample_repo_authors.json
    - sample_repo_challenge.json

    Returns dict mapping artifact key to its absolute path string.
    """
    out_path = Path(output_dir) if output_dir else Path(DEMO_CACHE_DIR)
    out_path.mkdir(parents=True, exist_ok=True)

    bundle_file = out_path / "sample_repo.bundle"
    index_file = out_path / "sample_repo_index.json"
    authors_file = out_path / "sample_repo_authors.json"
    challenge_file = out_path / "sample_repo_challenge.json"

    # Build repo in a temporary directory
    temp_dir = Path(tempfile.mkdtemp(prefix="studysync_build_"))
    try:
        # Initialize Git repo with 'main' branch
        subprocess.run(["git", "init", "-b", "main"], cwd=temp_dir, check=True)
        subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=temp_dir, check=True)
        subprocess.run(["git", "config", "core.eol", "lf"], cwd=temp_dir, check=True)
        subprocess.run(
            ["git", "config", "user.name", AUTHORS["aman"]["name"]], cwd=temp_dir, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", AUTHORS["aman"]["email"]], cwd=temp_dir, check=True
        )

        # 13 Deterministic commits across fixed timestamps
        # Commit 1: Aman creates utils/vector_ops.py base
        utils_dir = temp_dir / "utils"
        utils_dir.mkdir(parents=True, exist_ok=True)
        (utils_dir / "vector_ops.py").write_text(UTILS_VECTOR_OPS_BASE, encoding="utf-8", newline="\n")
        _commit_step(
            temp_dir,
            "aman",
            "2024-10-01 10:00:00 +0000",
            "Add initial vector math operations in utils.vector_ops",
        )

        # Commit 2: Aman adds normalize_vector
        (utils_dir / "vector_ops.py").write_text(UTILS_VECTOR_OPS_FULL, encoding="utf-8", newline="\n")
        _commit_step(
            temp_dir,
            "aman",
            "2024-10-01 11:00:00 +0000",
            "Add vector normalization function to utils.vector_ops",
        )

        # Commit 3: Aman creates utils/__init__.py
        (utils_dir / "__init__.py").write_text(UTILS_INIT_CONTENT, encoding="utf-8", newline="\n")
        _commit_step(
            temp_dir,
            "aman",
            "2024-10-01 12:00:00 +0000",
            "Export public vector math utilities from utils package",
        )

        # Commit 4: Aman creates models.py base
        (temp_dir / "models.py").write_text(MODELS_BASE, encoding="utf-8", newline="\n")
        _commit_step(
            temp_dir,
            "aman",
            "2024-10-01 13:00:00 +0000",
            "Define Student data model in models.py",
        )

        # Commit 5: Aman completes models.py
        (temp_dir / "models.py").write_text(MODELS_FULL, encoding="utf-8", newline="\n")
        _commit_step(
            temp_dir,
            "aman",
            "2024-10-01 14:00:00 +0000",
            "Add profile summary, student factory, and partner compatibility check",
        )

        # Commit 6: Priya implements cosine_similarity in similarity.py
        (temp_dir / "similarity.py").write_text(
            SIMILARITY_COSINE_ONLY, encoding="utf-8", newline="\n"
        )
        _commit_step(
            temp_dir,
            "priya",
            "2024-10-01 15:00:00 +0000",
            "Implement cosine_similarity metric using vector_ops",
        )

        # Commit 7: Priya adds jaccard_similarity
        (temp_dir / "similarity.py").write_text(
            SIMILARITY_WITH_JACCARD, encoding="utf-8", newline="\n"
        )
        _commit_step(
            temp_dir,
            "priya",
            "2024-10-01 16:00:00 +0000",
            "Add Jaccard similarity metric for student interest sets",
        )

        # Commit 8: Priya adds composite_similarity (buggy cosine remains)
        (temp_dir / "similarity.py").write_text(SIMILARITY_BUGGY, encoding="utf-8", newline="\n")
        _commit_step(
            temp_dir,
            "priya",
            "2024-10-01 17:00:00 +0000",
            "Add composite similarity combining skill vectors and interests",
        )

        # Commit 9: Rohan creates data_loader.py base
        (temp_dir / "data_loader.py").write_text(DATA_LOADER_BASE, encoding="utf-8", newline="\n")
        _commit_step(
            temp_dir,
            "rohan",
            "2024-10-01 18:00:00 +0000",
            "Add student record parser in data_loader.py",
        )

        # Commit 10: Rohan completes data_loader.py
        (temp_dir / "data_loader.py").write_text(DATA_LOADER_FULL, encoding="utf-8", newline="\n")
        _commit_step(
            temp_dir,
            "rohan",
            "2024-10-01 19:00:00 +0000",
            "Add built-in sample student cohort loader in data_loader.py",
        )

        # Commit 11: Aman implements ranking.py core
        (temp_dir / "ranking.py").write_text(RANKING_CORE, encoding="utf-8", newline="\n")
        _commit_step(
            temp_dir,
            "aman",
            "2024-10-01 20:00:00 +0000",
            "Implement candidate pair scoring and top_k_partners in ranking.py",
        )

        # Commit 12: Priya adds mutual matching in ranking.py
        (temp_dir / "ranking.py").write_text(RANKING_FULL, encoding="utf-8", newline="\n")
        _commit_step(
            temp_dir,
            "priya",
            "2024-10-01 21:00:00 +0000",
            "Add mutual cohort matching and reciprocal ranking in ranking.py",
        )

        # Commit 13: Rohan implements cli.py
        (temp_dir / "cli.py").write_text(CLI_CONTENT, encoding="utf-8", newline="\n")
        _commit_step(
            temp_dir,
            "rohan",
            "2024-10-01 22:00:00 +0000",
            "Add command-line interface entrypoint for studysync demo",
        )

        # Verify commit count
        rev_count = subprocess.check_output(
            ["git", "rev-list", "--count", "HEAD"], cwd=temp_dir, text=True
        ).strip()
        assert int(rev_count) == 13, f"Expected 13 commits, got {rev_count}"

        # 1. Create Git bundle
        if bundle_file.exists():
            bundle_file.unlink()
        subprocess.run(
            ["git", "bundle", "create", str(bundle_file), "--all"],
            cwd=temp_dir,
            check=True,
        )

        # 2. Generate RepoIndex metadata via AST indexer
        head_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=temp_dir, text=True
        ).strip()

        raw_index = index_repo_path(str(temp_dir), source_url=DEMO_REPO_URL)
        # Blank local_path, set from_cache = True, fix created_at for determinism
        indexed_files = [f.path for f in raw_index.files]
        sample_repo_index = RepoIndex(
            repo_id=raw_index.repo_id,
            source_url=DEMO_REPO_URL,
            local_path="",
            commit_sha=head_sha,
            files=raw_index.files,
            file_tree=raw_index.file_tree,
            total_py_files=raw_index.total_py_files,
            truncated=raw_index.truncated,
            from_cache=True,
            created_at="2024-10-01T22:00:00Z",
        )
        index_file.write_text(
            sample_repo_index.model_dump_json(indent=2),
            encoding="utf-8",
        )

        # 3. Generate Author Map & Authorship Stats
        author_map = extract_author_map(
            str(temp_dir),
            indexed_files,
            index=sample_repo_index,
        )
        author_stats = compute_authorship_stats(str(temp_dir), indexed_files)

        authors_payload = {
            "author_map": {
                author: [sym.model_dump() for sym in symbols]
                for author, symbols in sorted(author_map.items())
            },
            "authorship_stats": [stat.model_dump() for stat in author_stats],
        }
        authors_file.write_text(
            json.dumps(authors_payload, indent=2),
            encoding="utf-8",
        )

        # 4. Generate Challenge metadata
        challenge_payload = {
            "description": (
                "Fix ZeroDivisionError in cosine_similarity when either input vector has zero magnitude "
                "(e.g., all-zero vector). Return 0.0 in such cases."
            ),
            "target_file": "similarity.py",
            "function": "cosine_similarity",
            "starter_code": SIMILARITY_BUGGY,
            "test_code": CHALLENGE_TEST_CODE,
            "reference_solution": SIMILARITY_FIXED,
        }
        challenge_file.write_text(
            json.dumps(challenge_payload, indent=2),
            encoding="utf-8",
        )

        # 5. Self-verification with plain pytest in an isolated temp copy
        verify_dir = Path(tempfile.mkdtemp(prefix="studysync_verify_"))
        try:
            # Copy all files
            for py_file in indexed_files:
                src = temp_dir / py_file
                dst = verify_dir / py_file
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

            # Write test code
            test_file = verify_dir / "test_challenge.py"
            test_file.write_text(CHALLENGE_TEST_CODE, encoding="utf-8")

            # Write pytest.ini so pythonpath includes verify_dir
            ini_file = verify_dir / "pytest.ini"
            ini_file.write_text("[pytest]\npythonpath = .\n", encoding="utf-8")

            # Run with starter code -> must FAIL
            run_starter = subprocess.run(
                [sys.executable, "-m", "pytest", "test_challenge.py", "-q"],
                cwd=verify_dir,
                capture_output=True,
                text=True,
            )
            if run_starter.returncode == 0:
                raise RuntimeError(
                    f"Starter code unexpectedly passed tests!\nStdout: {run_starter.stdout}"
                )

            # Overwrite with reference solution -> must PASS
            (verify_dir / "similarity.py").write_text(SIMILARITY_FIXED, encoding="utf-8")
            run_ref = subprocess.run(
                [sys.executable, "-m", "pytest", "test_challenge.py", "-q"],
                cwd=verify_dir,
                capture_output=True,
                text=True,
            )
            if run_ref.returncode != 0:
                raise RuntimeError(
                    f"Reference solution failed tests!\nStdout: {run_ref.stdout}\nStderr: {run_ref.stderr}"
                )

        finally:
            cleanup_repo(str(verify_dir))

    finally:
        cleanup_repo(str(temp_dir))

    return {
        "bundle": str(bundle_file),
        "index": str(index_file),
        "authors": str(authors_file),
        "challenge": str(challenge_file),
    }


if __name__ == "__main__":
    result = build_sample_repo()
    print("Build successful:")
    for k, v in result.items():
        size = Path(v).stat().st_size
        print(f"  {k}: {v} ({size:,} bytes)")
