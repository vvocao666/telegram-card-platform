from types import SimpleNamespace

from services.ocr.source_consensus import repeated_pubg_source_consensus


def make_result(card: str, raw_text: str):
    return SimpleNamespace(cards=(card,), psn_cards=(), raw_text=raw_text)


def test_repeated_remote_and_ocrspace_card_is_consensus():
    card = "S07323-J4ED-EQTA-QCFYC"
    variant = "S07323-J4ED-EQTA-OCFYC"
    result = make_result(
        card,
        f"[REMOTE]\n{card}\n{card}\n[OCRSPACE]\n{card}\n{card}\n{variant}",
    )

    assert repeated_pubg_source_consensus(result) == card


def test_single_read_per_source_is_not_repeated_consensus():
    card = "S07323-J4ED-EQTA-QCFYC"
    result = make_result(card, f"[REMOTE]\n{card}\n[OCRSPACE]\n{card}")

    assert repeated_pubg_source_consensus(result) is None


def test_different_card_slot_prevents_consensus():
    card = "S07323-J4ED-EQTA-QCFYC"
    other = "S07323-ABCD-EFGH-JKLMN"
    result = make_result(
        card,
        f"[REMOTE]\n{card}\n{card}\n[OCRSPACE]\n{card}\n{card}\n{other}",
    )

    assert repeated_pubg_source_consensus(result) is None
