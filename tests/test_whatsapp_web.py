from decimal import Decimal

import httpx
import pytest

from isso_facilita.models import Product
from isso_facilita.publishers.whatsapp_web import WhatsAppWebPublisher


def product() -> Product:
    return Product(
        marketplace="aliexpress",
        product_id="123",
        title="SSD NVMe",
        product_url="https://example.com/product",
        affiliate_url="https://example.com/affiliate",
        image_url="https://example.com/image.jpg",
        price=Decimal("299.90"),
        original_price=Decimal("499.90"),
    )


@pytest.mark.asyncio
async def test_sends_to_local_bridge_without_exposing_token() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://127.0.0.1:3001/send"
        assert request.headers["authorization"] == "Bearer local-secret"
        assert request.read()
        return httpx.Response(200, json={"ok": True, "message_id": "abc"})

    publisher = WhatsAppWebPublisher(
        "http://127.0.0.1:3001/",
        "local-secret",
        transport=httpx.MockTransport(handler),
    )
    await publisher.publish(product(), "Oferta")


@pytest.mark.asyncio
async def test_bridge_error_does_not_expose_token() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"ok": False, "error": "WhatsApp desconectado"})

    publisher = WhatsAppWebPublisher(
        "http://127.0.0.1:3001",
        "local-secret",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(RuntimeError) as error:
        await publisher.publish(product(), "Oferta")

    assert "local-secret" not in str(error.value)
    assert "WhatsApp desconectado" in str(error.value)
