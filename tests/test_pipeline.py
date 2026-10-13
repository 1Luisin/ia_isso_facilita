from decimal import Decimal

import pytest

from isso_facilita.db import PublicationRepository
from isso_facilita.models import Product
from isso_facilita.providers.base import MarketplaceProvider
from isso_facilita.publishers.base import Publisher
from isso_facilita.service import PromotionService


class FakeProvider(MarketplaceProvider):
    name = "fake"

    async def discover(self) -> list[Product]:
        return [
            Product(
                marketplace="shopee",
                product_id="42",
                title="Monitor gamer 27 polegadas",
                product_url="https://example.com/product",
                affiliate_url="https://example.com/affiliate",
                image_url="",
                price=Decimal("900"),
                original_price=Decimal("1200"),
            )
        ]


class FakePublisher(Publisher):
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def publish(self, product: Product, message: str) -> None:
        self.messages.append(message)


@pytest.mark.asyncio
async def test_pipeline_publishes_once_and_deduplicates(tmp_path) -> None:
    publisher = FakePublisher()
    service = PromotionService(
        providers=[FakeProvider()],
        publisher=publisher,
        repository=PublicationRepository(tmp_path / "offers.db"),
        min_discount_percent=20,
        max_offers_per_run=5,
    )

    first = await service.run()
    second = await service.run()

    assert first.published == 1
    assert second.published == 0
    assert second.duplicates == 1
    assert len(publisher.messages) == 1


@pytest.mark.asyncio
async def test_dry_run_does_not_create_duplicate_history(tmp_path) -> None:
    publisher = FakePublisher()
    service = PromotionService(
        providers=[FakeProvider()],
        publisher=publisher,
        repository=PublicationRepository(tmp_path / "offers.db"),
        min_discount_percent=20,
        max_offers_per_run=5,
        record_publications=False,
    )

    first = await service.run()
    second = await service.run()

    assert first.published == 1
    assert second.published == 1
    assert second.duplicates == 0
    assert len(publisher.messages) == 2
