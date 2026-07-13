from decimal import Decimal
from pathlib import Path

from PIL import Image

from services.price.price_service import format_okx_prices, parse_okx_c2c_usdt_cny_prices
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
    for module_path in (Path("services/price/price_service.py"), Path("services/trc20/verify_service.py")):
        assert "services.runtime" not in module_path.read_text(encoding="utf-8")
