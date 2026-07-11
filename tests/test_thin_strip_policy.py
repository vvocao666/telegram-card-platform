from dataclasses import dataclass

from PIL import Image

from services.ocr.thin_strip_policy import choose_thin_strip_result, is_thin_strip_image


@dataclass(frozen=True)
class Result:
    cards: tuple[str, ...] = ()
    psn_cards: tuple[str, ...] = ()
    psn_uncertain: tuple[str, ...] = ()
    uncertain_count: int = 0


def test_thin_strip_detection_is_narrow(tmp_path):
    thin = tmp_path / "thin.jpg"
    regular = tmp_path / "regular.jpg"
    Image.new("RGB", (500, 80), "white").save(thin)
    Image.new("RGB", (500, 400), "white").save(regular)

    assert is_thin_strip_image(thin)
    assert not is_thin_strip_image(regular)


def test_valid_cloud_result_verifies_remote_conflict():
    remote = Result(cards=("S07324-N4RB-3744-V3Y8N",))
    cloud = Result(cards=("S07324-N4RB-3744-V3Y8M",))

    selected, changed = choose_thin_strip_result(remote, cloud, valid_card=lambda card: card.endswith("M"))

    assert selected is cloud
    assert changed is True


def test_uncertain_cloud_result_does_not_replace_remote():
    remote = Result(cards=("S07324-N4RB-3744-V3Y8N",))
    cloud = Result(cards=("S07324-N4RB-3744-V3Y8M",), uncertain_count=1)

    selected, changed = choose_thin_strip_result(remote, cloud, valid_card=lambda _card: True)

    assert selected is remote
    assert changed is False
