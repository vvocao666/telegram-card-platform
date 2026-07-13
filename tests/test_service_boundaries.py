from decimal import Decimal
from pathlib import Path

from PIL import Image

from services.price.price_service import format_okx_prices, parse_okx_c2c_usdt_cny_prices
from services.status.status_service import StatusPanelSnapshot, render_status_panel
from services.trc20.verify_service import extract_trc20_address, make_trc20_verify_image


def test_price_service_preserves_five_level_format():
    payload = {"data": {"sell": [{"price": value} for value in ("6.80", "6.81", "6.82", "6.83", "6.84", "6.85")]}}

    prices = parse_okx_c2c_usdt_cny_prices(payload)

    assert prices == [Decimal("6.80"), Decimal("6.81"), Decimal("6.82"), Decimal("6.83"), Decimal("6.84")]
    assert format_okx_prices(prices, "OKX C2C卖单").splitlines()[-1] == "来源：OKX C2C卖单"


def test_trc20_service_preserves_address_and_image_contract():
    address = "T" + "A" * 33

    assert extract_trc20_address(f"收款地址 {address}") == address
    image_data = make_trc20_verify_image(address)
    with Image.open(image_data) as image:
        assert image.size == (860, 300)
        assert image.format == "PNG"


def test_service_modules_do_not_import_runtime():
    for module_path in (
        Path("services/price/price_service.py"),
        Path("services/status/status_service.py"),
        Path("services/status/system_info.py"),
        Path("services/trc20/verify_service.py"),
    ):
        assert "services.runtime" not in module_path.read_text(encoding="utf-8")


def test_status_service_preserves_panel_contract():
    text = render_status_panel(
        StatusPanelSnapshot(
            service_state="active",
            branch="main",
            commit="abc1234",
            memory="12.5 MB",
            uptime="2小时3分钟",
            ledger_exists=True,
            remote_label="RTX5070",
            remote_enabled=True,
            worker_ok=True,
            worker_status="ok",
            worker_gpu="RTX5070",
            worker_engine="paddlex_ocr",
            remote_url="127.0.0.1:8000",
            avg_remote_latency_ms=600,
            last_success="12:00:00",
            last_failed="无",
            last_error="无",
            current_provider="RTX5070",
            ocrspace_available=True,
            remote_calls=4,
            remote_success=3,
            remote_failed=1,
            fallback_count=1,
            cache_hit_rate="25.0%",
            enhanced_rate="50.0%",
            image_count=2,
            card_count=2,
            pubg_count=1,
            psn_count=1,
            duplicate_count=1,
            worker_extra=["opencv: True"],
        )
    )

    assert "状态：运行中" in text
    assert "服务：telegram-card-platform active/running" in text
    assert "GPU：RTX5070" in text
    assert "opencv: True" in text
    assert "缓存命中率：25.0%" in text
    assert "图片：2 张" in text
