"""Shared helpers. Keep query normalization in one place so the read side and the
ingest side clean text identically (otherwise 'IP' and 'ip' could miss each other).
"""


def normalize(text: str) -> str:
    """Lowercase and trim. Used for both stored queries and lookup prefixes."""
    return text.strip().lower()
