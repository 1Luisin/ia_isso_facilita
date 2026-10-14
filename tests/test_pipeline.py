from decimal import Decimal

import pytest

from isso_facilita.curation import CurationResult
from isso_facilita.db import PublicationRepository
from isso_facilita.models import Product
from isso_facilita.providers.base import MarketplaceProvider
from isso_facilita.publishers.base import MultiPublisher, Publisher
from isso_facilita.service import PromotionService, is_technology


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


class FailingPublisher(Publisher):
    destination = "failing"

    def __init__(self) -> None:
        self.should_fail = True
        self.calls = 0

    async def publish(self, product: Product, message: str) -> None:
        self.calls += 1
        if self.should_fail:
            raise RuntimeError("indisponível")


class RejectingCurator:
    async def curate(self, product: Product) -> CurationResult:
        return CurationResult(
            relevant=False,
            relevance_score=20,
            headline="",
            description="",
            reason=f"{product.title} não combina com a página",
        )


def test_technology_filter_rejects_tarot_with_mouse_in_title() -> None:
    item = Product(
        marketplace="aliexpress",
        product_id="tarot",
        title="Baralho de tarô Mimi Mouse, oracle, jogo de mesa",
        product_url="https://example.com/product",
        affiliate_url="https://example.com/affiliate",
        image_url="",
        price=Decimal("20"),
        original_price=Decimal("40"),
    )

    assert not is_technology(item)


@pytest.mark.asyncio
async def test_ai_curation_can_reject_a_keyword_match(tmp_path) -> None:
    publisher = FakePublisher()
    service = PromotionService(
        providers=[FakeProvider()],
        publisher=publisher,
        repository=PublicationRepository(tmp_path / "offers.db"),
        min_discount_percent=20,
        max_offers_per_run=5,
        curator=RejectingCurator(),
        ai_relevance_threshold=75,
    )

    result = await service.run()

    assert result.published == 0
    assert result.ai_rejected == 1
    assert publisher.messages == []


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


@pytest.mark.asyncio
async def test_retries_only_destination_that_failed(tmp_path) -> None:
    successful = FakePublisher()
    successful.destination = "successful"
    failing = FailingPublisher()
    service = PromotionService(
        providers=[FakeProvider()],
        publisher=MultiPublisher([successful, failing]),
        repository=PublicationRepository(tmp_path / "offers.db"),
        min_discount_percent=20,
        max_offers_per_run=5,
    )

    first = await service.run()
    failing.should_fail = False
    second = await service.run()
    third = await service.run()

    assert first.published == 1
    assert first.failures == 1
    assert second.published == 1
    assert third.duplicates == 1
    assert len(successful.messages) == 1
    assert failing.calls == 2
