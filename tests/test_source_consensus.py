from types import SimpleNamespace

from services.ocr.source_consensus import repeated_pubg_source_consensus


def make_result(card: str, raw_text: str, **kwargs):
    return SimpleNamespace(cards=(card,), psn_cards=(), raw_text=raw_text, **kwargs)


def test_repeated_remote_and_ocrspace_card_is_consensus():
    card = "S07323-J4ED-EQTA-QCFYC"
    variant = "S07323-J4ED-EQTA-OCFYC"
    result = make_result(
        card,
        f"[REMOTE]\n{card}\n{card}\n[OCRSPACE]\n{card}\n{card}\n{variant}",
    )

    assert repeated_pubg_source_consensus(result) == card


def test_repeated_remote_and_single_matching_ocrspace_card_is_consensus():
    card = "S07336-Z483-CNEE-W6C5W"
    same_slot_variant = "S07336-ZA83-CNEE-W6C5W"
    result = make_result(
        card,
        (
            f"[REMOTE]\n{card}\n{card}\n"
            f"[OCRSPACE]\n{card}\nS07336-Z483-NEE-W6C5W\n{same_slot_variant}"
        ),
    )

    assert repeated_pubg_source_consensus(result) == card


def test_duplicate_remote_body_with_damaged_first_glyph_is_consensus():
    card = "S07336-5XAW-QTQ5-S5X48"
    result = make_result(
        card,
        (
            "[REMOTE]\n507336-5XAW-QTQ5-S5X48\n607336-5XAW-QTQ5-S5X48\n"
            f"[OCRSPACE]\n{card}\nS07336-5XAW-OTOS-S5X48\n"
            "S07336-5XAW-OTOS-SSX48"
        ),
    )

    assert repeated_pubg_source_consensus(result) == card


def test_different_remote_body_with_damaged_first_glyph_prevents_consensus():
    card = "S07336-5XAW-QTQ5-S5X48"
    result = make_result(
        card,
        (
            "[REMOTE]\n507336-5XAW-QTQ5-S5X48\n"
            "607336-5XAW-ABCD-EFGHJ\n"
            f"[OCRSPACE]\n{card}"
        ),
    )

    assert repeated_pubg_source_consensus(result) is None


def test_single_read_per_source_is_not_repeated_consensus():
    card = "S07323-J4ED-EQTA-QCFYC"
    result = make_result(card, f"[REMOTE]\n{card}\n[OCRSPACE]\n{card}")

    assert repeated_pubg_source_consensus(result) is None


def test_original_and_enhanced_gpu_evidence_plus_cloud_is_consensus():
    card = "S07336-4JB5-3TC6-XPA7R"
    result = make_result(
        card,
        f"[REMOTE]\n{card}\n[OCRSPACE]\n{card}\nS07336-4JB5-31C6-XPA7R",
        remote_original_card_scores=((card, 0.996),),
        remote_enhanced_card_scores=((card, 0.998),),
    )

    assert repeated_pubg_source_consensus(result) == card


def test_high_confidence_original_and_enhanced_gpu_match_beats_tail_only_cloud_noise():
    card = "S07336-B7KS-S3NN-Q38Q8"
    result = make_result(
        card,
        (
            f"[REMOTE]\n{card}\n"
            "[OCRSPACE]\nS07336-B7KS-S3NN-03898\nS07336-B7KS-S3NN-Q38QG"
        ),
        remote_original_card_scores=((card, 0.9823944568634033),),
        remote_enhanced_card_scores=((card, 0.9910047054290771),),
    )

    assert repeated_pubg_source_consensus(result) == card


def test_low_confidence_gpu_match_does_not_override_tail_only_cloud_noise():
    card = "S07336-B7KS-S3NN-Q38Q8"
    result = make_result(
        card,
        f"[REMOTE]\n{card}\n[OCRSPACE]\nS07336-B7KS-S3NN-Q38QG",
        remote_original_card_scores=((card, 0.96),),
        remote_enhanced_card_scores=((card, 0.99),),
    )

    assert repeated_pubg_source_consensus(result) is None


def test_dual_gpu_match_does_not_override_cloud_conflict_in_another_segment():
    card = "S07336-B7KS-S3NN-Q38Q8"
    result = make_result(
        card,
        f"[REMOTE]\n{card}\n[OCRSPACE]\nS07336-B7KS-ABCD-Q38Q8",
        remote_original_card_scores=((card, 0.99),),
        remote_enhanced_card_scores=((card, 0.99),),
    )

    assert repeated_pubg_source_consensus(result) is None


def test_repeated_adjacent_line_reconstruction_rejects_cloud_fragment_reordering():
    card = "S07336-NU64-MG2H-E8MKV"
    reordered = "S07336-NU64-MKVM-G2HE8"
    result = make_result(
        card,
        (
            "[REMOTE]\n"
            "S07336-NU64-MG2H-E8\nMKV\n"
            "S07336-NU64-MG2H-E8\nMKV\n"
            f"[OCRSPACE]\n{card}\n{reordered}"
        ),
    )

    assert repeated_pubg_source_consensus(result) == card


def test_single_adjacent_line_reconstruction_is_not_source_consensus():
    card = "S07336-NU64-MG2H-E8MKV"
    result = make_result(
        card,
        f"[REMOTE]\nS07336-NU64-MG2H-E8\nMKV\n[OCRSPACE]\n{card}",
    )

    assert repeated_pubg_source_consensus(result) is None


def test_non_adjacent_fragments_are_not_source_consensus():
    card = "S07336-NU64-MG2H-E8MKV"
    result = make_result(
        card,
        (
            "[REMOTE]\nS07336-NU64-MG2H-E8\nOTHER\nMKV\n"
            "S07336-NU64-MG2H-E8\nOTHER\nMKV\n"
            f"[OCRSPACE]\n{card}"
        ),
    )

    assert repeated_pubg_source_consensus(result) is None


def test_one_gpu_variant_disagreement_does_not_create_consensus():
    card = "S07336-4JB5-3TC6-XPA7R"
    result = make_result(
        card,
        f"[REMOTE]\n{card}\n[OCRSPACE]\n{card}",
        remote_original_card_scores=((card, 0.996),),
        remote_enhanced_card_scores=(("S07336-4JB5-31C6-XPA7R", 0.998),),
    )

    assert repeated_pubg_source_consensus(result) is None


def test_different_card_slot_prevents_consensus():
    card = "S07323-J4ED-EQTA-QCFYC"
    other = "S07323-ABCD-EFGH-JKLMN"
    result = make_result(
        card,
        f"[REMOTE]\n{card}\n{card}\n[OCRSPACE]\n{card}\n{card}\n{other}",
    )

    assert repeated_pubg_source_consensus(result) is None
