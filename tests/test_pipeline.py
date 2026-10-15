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
                price=Decimal("450"),
                original_price=Decimal("1200"),
            )
        ]


class FakeMixedProvider(MarketplaceProvider):
    name = "mixed"

    async def discover(self) -> list[Product]:
        promotional = (await FakeProvider().discover())[0]
        regular = Product(
            marketplace="aliexpress",
            product_id="regular-1",
            title="Fones Bluetooth com gancho ajustável",
            product_url="https://example.com/regular",
            affiliate_url="https://example.com/regular-affiliate",
            image_url="",
            price=Decimal("150"),
            original_price=Decimal("150"),
        )
        return [regular, promotional]


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


class FailingCurator:
    def __init__(self) -> None:
        self.product_ids: list[str] = []

    async def curate(self, product: Product) -> CurationResult:
        self.product_ids.append(product.product_id)
        raise RuntimeError("resposta inválida")


class FakeManyProductsProvider(MarketplaceProvider):
    name = "many"

    async def discover(self) -> list[Product]:
        return [
            Product(
                marketplace="aliexpress",
                product_id=str(index),
                title=f"Mouse sem fio modelo {index}",
                product_url=f"https://example.com/product/{index}",
                affiliate_url=f"https://example.com/affiliate/{index}",
                image_url="",
                price=Decimal(100 - index),
                original_price=Decimal("100"),
            )
            for index in range(1, 5)
        ]


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
    decisions: list[tuple[Product, CurationResult | None, bool | None, int, str]] = []
    service = PromotionService(
        providers=[FakeProvider()],
        publisher=publisher,
        repository=PublicationRepository(tmp_path / "offers.db"),
        min_discount_percent=20,
        max_offers_per_run=5,
        curator=RejectingCurator(),
        ai_relevance_threshold=75,
        ai_decision_recorder=lambda *decision: decisions.append(decision),
    )

    result = await service.run()

    assert result.published == 0
    assert result.ai_rejected == 1
    assert publisher.messages == []
    assert len(decisions) == 1
    assert decisions[0][0].affiliate_url == "https://example.com/affiliate"
    assert decisions[0][2] is False
    assert decisions[0][3] == 75


@pytest.mark.asyncio
async def test_real_publication_pauses_when_ai_is_disabled(tmp_path) -> None:
    publisher = FakePublisher()
    service = PromotionService(
        providers=[FakeProvider()],
        publisher=publisher,
        repository=PublicationRepository(tmp_path / "offers.db"),
        min_discount_percent=20,
        max_offers_per_run=1,
        require_ai_for_publication=True,
    )

    result = await service.run()

    assert result.ai_paused == 1
    assert result.discovered == 0
    assert result.published == 0
    assert publisher.messages == []


@pytest.mark.asyncio
async def test_ai_audit_failure_does_not_change_curation_result(tmp_path) -> None:
    def failing_recorder(*_args: object) -> None:
        raise OSError("disco indisponível")

    service = PromotionService(
        providers=[FakeProvider()],
        publisher=FakePublisher(),
        repository=PublicationRepository(tmp_path / "offers.db"),
        min_discount_percent=20,
        max_offers_per_run=5,
        curator=RejectingCurator(),
        ai_relevance_threshold=75,
        ai_decision_recorder=failing_recorder,
    )

    result = await service.run()

    assert result.ai_evaluated == 1
    assert result.ai_rejected == 1
    assert result.failures == 0


@pytest.mark.asyncio
async def test_ai_curation_advances_candidates_after_failed_cycle(tmp_path) -> None:
    curator = FailingCurator()
    service = PromotionService(
        providers=[FakeManyProductsProvider()],
        publisher=FakePublisher(),
        repository=PublicationRepository(tmp_path / "offers.db"),
        min_discount_percent=0,
        max_offers_per_run=1,
        curator=curator,
        max_ai_evaluations_per_run=2,
    )

    first = await service.run()
    first_product_ids = set(curator.product_ids)
    curator.product_ids.clear()
    second = await service.run()

    assert first.ai_evaluated == 2
    assert second.ai_evaluated == 2
    assert first_product_ids.isdisjoint(curator.product_ids)


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


@pytest.mark.asyncio
async def test_pipeline_includes_and_interleaves_regular_price_products(tmp_path) -> None:
    publisher = FakePublisher()
    service = PromotionService(
        providers=[FakeMixedProvider()],
        publisher=publisher,
        repository=PublicationRepository(tmp_path / "offers.db"),
        min_discount_percent=20,
        max_offers_per_run=2,
        include_non_promotional_products=True,
    )

    result = await service.run()

    assert result.eligible == 2
    assert result.published == 2
    assert "Desconto:" in publisher.messages[0]
    assert "✦ Preço: R$ 150,00" in publisher.messages[1]
