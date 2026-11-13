"""Load the records used by the VivaVoce offline demo."""

import json
from pathlib import Path

ENCODING = "utf-8"


def load_records(path: str) -> list[dict]:
    """Return records from a JSON object containing a records field."""
    payload = json.loads(Path(path).read_text(encoding=ENCODING))
    # Planted edge-case bug: a valid top-level JSON list has no .get() method.
    return payload.get("records", [])
