from services.ocr.pubg_candidate_merge import incomplete_pubg_prefix_keys, merge_text_and_worker_pubg_cards


def test_worker_cards_are_kept_when_not_conflicting_with_text_rebuild():
    merged = merge_text_and_worker_pubg_cards(
        text_cards=["S07336-ZMBN-5CWZ-GTRVF"],
        worker_cards=[
            "S07336-QFTZ-BPKM-BR6LV",
            "S07336-K88S-GD9S-FXS2U",
            "S07336-ZMBN-5CWZ-GTRVF",
        ],
    )

    assert merged.cards == (
        "S07336-ZMBN-5CWZ-GTRVF",
        "S07336-QFTZ-BPKM-BR6LV",
        "S07336-K88S-GD9S-FXS2U",
    )
    assert merged.dropped == tuple()


def test_worker_conflict_with_same_slot_text_rebuild_is_dropped():
    merged = merge_text_and_worker_pubg_cards(
        text_cards=["S07324-JT74-WL64-AA27X"],
        worker_cards=[
            "S07324-JT74-WL6G-4AA27",
            "S07324-JT74-WL64-AA27X",
        ],
    )

    assert merged.cards == ("S07324-JT74-WL64-AA27X",)
    assert len(merged.dropped) == 1
    assert merged.dropped[0].card == "S07324-JT74-WL6G-4AA27"
    assert merged.dropped[0].reason == "conflict_with_line_wrap"


def test_incomplete_text_line_blocks_worker_guess():
    blocked = incomplete_pubg_prefix_keys(["card: S07304-94VF-NG88-", "JE"])
    merged = merge_text_and_worker_pubg_cards(
        text_cards=["S07304-UM3A-RHGF-SY5RQ"],
        worker_cards=["S07304-94VF-NG88-JES07"],
        blocked_prefix_keys=blocked,
    )

    assert merged.cards == ("S07304-UM3A-RHGF-SY5RQ",)
    assert len(merged.dropped) == 1
    assert merged.dropped[0].card == "S07304-94VF-NG88-JES07"
    assert merged.dropped[0].reason == "conflict_with_incomplete_text_line"


def test_incomplete_text_line_blocks_worker_guess_without_text_cards():
    blocked = incomplete_pubg_prefix_keys(["card: S07304-94VF-NG88-", "JE"])
    merged = merge_text_and_worker_pubg_cards(
        text_cards=[],
        worker_cards=["S07304-94VF-NG88-JES07"],
        blocked_prefix_keys=blocked,
    )

    assert merged.cards == tuple()
    assert len(merged.dropped) == 1
    assert merged.dropped[0].reason == "conflict_with_incomplete_text_line"
