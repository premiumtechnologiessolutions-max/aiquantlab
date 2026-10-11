from __future__ import annotations

import re

_IDENTIFIER_PATTERN = re.compile(
    r"[a-z][a-z0-9_]*",
)


def normalize_identifier_text(
    value: str,
) -> str:
    """Normalize identifier text without validating its final shape."""

    return (
        value.strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
    )


def normalize_identifier(
    value: str,
    *,
    field_name: str,
) -> str:
    """Normalize and validate one agent, task, or board identifier."""

    normalized = normalize_identifier_text(value)

    if not _IDENTIFIER_PATTERN.fullmatch(normalized):
        raise ValueError(
            f"{field_name} must start with a letter and contain "
            "only lowercase letters, numbers, and underscores.",
        )

    return normalized


def normalize_spoken_text(
    value: str,
) -> str:
    """Normalize written or spoken user text for reliable matching."""

    return " ".join(
        value.strip().casefold().split(),
    )
