from services.ocr.prefix_recovery_policy import (
    choose_cloud_same_slot_card,
    requires_cloud_confirmation,
)


def test_complete_five_prefix_pubg_requires_cloud_confirmation() -> None:
    assert requires_cloud_confirmation("密码：507999-ABCD-EFGH-IJKLM") is True
    assert requires_cloud_confirmation("S07999-ABCD-EFGH-IJKL") is False


def test_complete_recovered_prefix_on_second_ocr_line_requires_cloud_confirmation() -> None:
    raw_text = "卡号：\n507324-Z4ZH-54Y7-NBRSB\n密码："
    assert requires_cloud_confirmation(raw_text) is True


def test_four_character_tail_does_not_match_pubg_structure() -> None:
    assert requires_cloud_confirmation("507999-ABCD-EFGH-IJKL") is False


def test_cloud_result_can_replace_same_slot_recovered_prefix_candidate() -> None:
    assert choose_cloud_same_slot_card(
        ("S07324-Z4ZH-54Y7-NBRSB",),
        ("S07324-Z4ZH-S4Y7-NBRSB",),
        valid_card=lambda value: value.startswith("S07"),
    ) == "S07324-Z4ZH-S4Y7-NBRSB"


def test_cloud_result_cannot_replace_an_unrelated_card() -> None:
    assert choose_cloud_same_slot_card(
        ("S07324-Z4ZH-54Y7-NBRSB",),
        ("S07336-AAAA-BBBB-CCCCC",),
        valid_card=lambda value: value.startswith("S07"),
    ) is None
