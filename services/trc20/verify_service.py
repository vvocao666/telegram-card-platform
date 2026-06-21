from __future__ import annotations

import re


TRON_ADDRESS_RE = re.compile(r"^T[1-9A-HJ-NP-Za-km-z]{33}$")


def is_tron_address(value: str) -> bool:
    """只做地址格式校验；链上转账验证留给后续 API 接入。"""

    return bool(TRON_ADDRESS_RE.fullmatch(value.strip()))
