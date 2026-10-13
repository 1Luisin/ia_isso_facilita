from decimal import Decimal

import httpx
import pytest

from isso_facilita.models import Product
from isso_facilita.publishers.whatsapp import WhatsAppPublisher


def product(image_url: str = "https://example.com/image.jpg") -> Product:
    return Product(
        marketplace="shopee",
        product_id="123",
        title="SSD NVMe",
        product_url="https://example.com/product",
        affiliate_url="https://example.com/affiliate",
        image_url=image_url,
        price=Decimal("299.90"),
        original_price=Decimal("499.90"),
    )


def test_builds_group_image_payload() -> None:
    publisher = WhatsAppPublisher("token", "phone-id", "group-id")
    payload = publisher.build_payload(product(), "Oferta")

    assert payload["recipient_type"] == "group"
    assert payload["to"] == "group-id"
    assert payload["type"] == "image"
    assert payload["image"] == {
        "link": "https://example.com/image.jpg",
        "caption": "Oferta",
    }


@pytest.mark.asyncio
async def test_publishes_through_meta_messages_endpoint() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://graph.facebook.com/v25.0/phone-id/messages"
        assert request.headers["authorization"] == "Bearer token"
        return httpx.Response(200, json={"messages": [{"id": "wamid.123"}]})

    publisher = WhatsAppPublisher(
        "token",
        "phone-id",
        "group-id",
        transport=httpx.MockTransport(handler),
    )

    await publisher.publish(product(image_url=""), "Oferta")
