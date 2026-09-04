from __future__ import annotations

import re


_WRAPPED_FIRST_GROUP_RE = re.compile(
    r"(?<![A-Z0-9-])([A-Z0-9]{1,3})\r?\n([A-Z0-9]{1,3})"
    r"(?=[\s_]*-[\s_]*[A-Z0-9]{4}[\s_]*-[\s_]*[A-Z0-9]{4}(?![A-Z0-9-]))"
)
_MISSING_LABEL_SEPARATOR_RE = re.compile(
    r"([A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4})(?=PSN\d)"
)


def normalize_psn_ocr_layout(text: str) -> str:
    """Restore safe separators and a first group split across adjacent OCR lines."""

    def replace(match: re.Match[str]) -> str:
        left, right = match.groups()
        return left + right if len(left) + len(right) == 4 else match.group(0)

    text = _MISSING_LABEL_SEPARATOR_RE.sub(r"\1 ", text)
    return _WRAPPED_FIRST_GROUP_RE.sub(replace, text)
