from __future__ import annotations

import logging
from decimal import Decimal

import httpx

from services.calculator import format_calc_result


logger = logging.getLogger("telegram-card-platform")
OKX_C2C_USDT_CNY_URL = (
    "https://www.okx.com/v3/c2c/tradingOrders/books"
    "?quoteCurrency=cny&baseCurrency=usdt&side=sell&paymentMethod=all&userType=all&showTrade=false"
)
OKX_EXCHANGE_RATE_URL = "https://www.okx.com/api/v5/market/exchange-rate"
OKX_HTTP_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def parse_okx_c2c_usdt_cny_prices(payload: dict, limit: int = 5) -> list[Decimal]:
    sell_orders = payload.get("data", {}).get("sell", [])
    if not sell_orders:
        raise ValueError("empty OKX C2C sell order book")
    prices: list[Decimal] = []
    for order in sell_orders:
        price = order.get("price")
        if price is None:
            continue
        prices.append(Decimal(str(price)))
        if len(prices) >= limit:
            break
    if not prices:
        raise ValueError("missing OKX C2C prices")
    return prices


def parse_okx_exchange_rate_price(payload: dict) -> Decimal:
    data = payload.get("data", [])
    if not data:
        raise ValueError("empty OKX exchange-rate data")
    price = data[0].get("usdCny")
    if price is None:
        raise ValueError("missing OKX usdCny")
    return Decimal(str(price))


def format_okx_prices(prices: list[Decimal], source: str) -> str:
    lines = ["欧意USDT/CNY 最新5档"]
    lines.extend(f"{index}. {format_calc_result(price)}" for index, price in enumerate(prices, start=1))
    lines.append(f"来源：{source}")
    return "\n".join(lines)


def is_price_command(text: str) -> bool:
    normalized = text.strip()
    lowered = normalized.lower()
    return normalized == "币价" or lowered in {"bj", "z0"} or normalized == "/price"


def is_realtime_rate_command(text: str) -> bool:
    return text.strip() == "设置实时汇率"


async def fetch_okx_usdt_cny_prices() -> tuple[list[Decimal], str]:
    async with httpx.AsyncClient(timeout=15, headers=OKX_HTTP_HEADERS) as client:
        try:
            response = await client.get(OKX_C2C_USDT_CNY_URL)
            response.raise_for_status()
            return parse_okx_c2c_usdt_cny_prices(response.json(), limit=5), "OKX C2C卖单"
        except Exception:
            logger.exception("OKX C2C USDT/CNY price fetch failed, falling back to exchange-rate")
        response = await client.get(OKX_EXCHANGE_RATE_URL)
        response.raise_for_status()
        return [parse_okx_exchange_rate_price(response.json())], "OKX官方USD/CNY汇率"


async def reply_okx_price(message) -> None:
    try:
        prices, source = await fetch_okx_usdt_cny_prices()
    except Exception:
        logger.exception("OKX USDT/CNY price fetch failed")
        await message.reply_text("币价获取失败，请稍后再试。")
        return
    await message.reply_text(format_okx_prices(prices, source))
