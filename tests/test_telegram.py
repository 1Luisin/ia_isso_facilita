from dataclasses import replace
from decimal import Decimal

import httpx
import pytest

from isso_facilita.models import Product
from isso_facilita.publishers.telegram import TelegramPublisher


def product() -> Product:
    return Product(
        marketplace="shopee",
        product_id="123",
        title="SSD NVMe",
        product_url="https://example.com/product",
        affiliate_url="https://example.com/affiliate",
        image_url="",
        price=Decimal("299.90"),
        original_price=Decimal("499.90"),
    )


@pytest.mark.asyncio
async def test_long_caption_is_sent_as_text_message() -> None:
    request: httpx.Request | None = None

    async def handler(received: httpx.Request) -> httpx.Response:
        nonlocal request
        request = received
        return httpx.Response(200, json={"ok": True})

    item = replace(product(), image_url="https://example.com/product.jpg")
    publisher = TelegramPublisher(
        "secret-token",
        "@channel",
        transport=httpx.MockTransport(handler),
    )

    await publisher.publish(item, "x" * 1025)

    assert request is not None
    assert request.url.path.endswith("/sendMessage")


@pytest.mark.asyncio
async def test_telegram_error_does_not_expose_token() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"ok": False, "description": "Unauthorized"})

    publisher = TelegramPublisher(
        "secret-token",
        "@channel",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(RuntimeError) as error:
        await publisher.publish(product(), "Oferta")

    assert "secret-token" not in str(error.value)
    assert "Unauthorized" in str(error.value)
