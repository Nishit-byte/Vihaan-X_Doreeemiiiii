"""Defaults for the VivaVoce offline repository demo."""

MAX_RECORDS = 500
DEFAULT_SCORE = 0.0


def normalize_name(name: str) -> str:
    """Normalize a display name for stable lookups."""
    return " ".join(name.casefold().split())
