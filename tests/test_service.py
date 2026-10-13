from decimal import Decimal

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
    assert "R$ 300,00" in message
    assert "40% OFF" in message
    assert "https://example.com/affiliate" in message
    assert "link de afiliado" in message
