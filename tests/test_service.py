from decimal import Decimal

from isso_facilita.curation import CurationResult
from isso_facilita.models import Product
from isso_facilita.service import compose_message, is_technology


def product(**overrides: object) -> Product:
    values = {
        "marketplace": "shopee",
        "product_id": "1",
        "title": "SSD NVMe 1 TB",
        "product_url": "https://example.com/product",
        "affiliate_url": "https://example.com/affiliate",
        "image_url": "https://example.com/image.jpg",
        "price": Decimal("300"),
        "original_price": Decimal("500"),
    }
    values.update(overrides)
    return Product(**values)  # type: ignore[arg-type]


def test_calculates_discount() -> None:
    assert product().discount_percent == 40.0


def test_recognizes_technology_with_accents() -> None:
    assert is_technology(product(title="Memória RAM DDR5 para computador"))
    assert not is_technology(product(title="Tênis esportivo"))


def test_message_contains_disclosure_and_affiliate_link() -> None:
    message = compose_message(product())
    assert "✿ ISSO FACILITA ✿" in message
    assert "R$ 300,00" in message
    assert "40% OFF" in message
    assert "https://example.com/affiliate" in message
    assert "link de afiliado" in message.lower()


def test_curated_copy_preserves_official_product_fields() -> None:
    item = product()
    curation = CurationResult(
        relevant=True,
        relevance_score=96,
        headline="✦ Mais agilidade para o seu computador",
        description="Um achadinho útil para deixar sua rotina digital mais prática.",
        reason="Armazenamento é relevante para o público da página.",
    )

    message = compose_message(item, curation)

    assert curation.headline in message
    assert curation.description in message
    assert item.title in message
    assert "R$ 500,00" in message
    assert "R$ 300,00" in message
    assert "40% OFF" in message
    assert item.affiliate_url in message
