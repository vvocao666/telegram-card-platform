from pathlib import Path

from scripts.check_deploy_consistency import digest_business_source


ROOT = Path(__file__).resolve().parents[1]


def test_deployment_modes_share_the_same_business_source() -> None:
    assert len(digest_business_source()) == 64
    assert (ROOT / "deploy/cloud/install.sh").is_file()
    assert (ROOT / "deploy/cloud/update.sh").is_file()
    assert (ROOT / "deploy/owner-hybrid/install.sh").is_file()


def test_deployment_examples_only_change_remote_ocr_configuration() -> None:
    cloud = (ROOT / ".env.cloud.example").read_text(encoding="utf-8")
    hybrid = (ROOT / ".env.owner-hybrid.example").read_text(encoding="utf-8")
    assert "REMOTE_OCR_ENABLED=false" in cloud
    assert "REMOTE_OCR_ENABLED=true" in hybrid
    assert "YOUR_PRIVATE_WORKER" in hybrid
