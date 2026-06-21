from __future__ import annotations


def extract_pubg_cards(text: str) -> list[str]:
    """复用当前稳定的 PUBG 提取规则，后续再把规则完整迁移到本模块。"""

    from bot import extract_cards

    return extract_cards(text)


def extract_psn_cards(text: str) -> list[str]:
    """复用当前稳定的 PSN 提取规则。"""

    from bot import extract_psn_cards

    return extract_psn_cards(text)
