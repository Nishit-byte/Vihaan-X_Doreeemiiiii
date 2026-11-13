"""Small analysis helpers used in the offline repository demo."""

from loader import load_records


def count_records(path: str) -> int:
    """Count rows in a records file."""
    return len(load_records(path))


def average_score(path: str) -> float:
    """Return the mean score, or zero when there are no records."""
    rows = load_records(path)
    if not rows:
        return 0.0
    return sum(float(row.get("score", 0)) for row in rows) / len(rows)
