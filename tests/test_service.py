from decimal import Decimal

from isso_facilita.curation import CurationResult
from isso_facilita.models import Product
from isso_facilita.service import (
    classify_content_bucket,
    compose_message,
    is_technology,
    order_for_editorial_rotation,
)


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
    assert is_technology(product(title="Figura decorativa Kuromi Sanrio kawaii"))
    assert is_technology(product(title="Action figure de personagem de anime chibi"))
    assert not is_technology(product(title="Tênis esportivo"))


def test_promotional_message_contains_prices_discount_and_affiliate_link() -> None:
    message = compose_message(product())
    assert "✿ ISSO FACILITA ✿" in message
    assert "R$ 300,00" in message
    assert "40% OFF" in message
    assert "https://example.com/affiliate" in message
    assert "Preço e estoque podem mudar" not in message
    assert "podemos receber uma comissão" not in message


def test_regular_price_message_does_not_invent_discount() -> None:
    message = compose_message(product(price=Decimal("300"), original_price=Decimal("300")))

    assert "✦ Preço: R$ 300,00" in message
    assert "⊹ De:" not in message
    assert "✦ Por:" not in message
    assert "Desconto:" not in message


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


def test_curated_product_name_replaces_noisy_marketplace_title_in_message() -> None:
    item = product(title="Ornamento de Calendário de Bolo Hello Kitty Figura de Anime")
    curation = CurationResult(
        relevant=True,
        relevance_score=100,
        headline="Hello Kitty ajudando a organizar a mesa ✿",
        description="Mini calendário da Hello Kitty com suporte para celular.",
        reason="Objeto identificado pelo título e pela imagem.",
        category="general",
        product_name="Mini calendário da Hello Kitty com suporte para celular",
    )

    message = compose_message(item, curation)

    assert "𖥔 Produto: Mini calendário da Hello Kitty com suporte para celular" in message
    assert "Ornamento de Calendário de Bolo" not in message


def test_non_tech_figure_uses_general_achadinho_label() -> None:
    item = product(title="Figura decorativa Cinnamoroll kawaii")
    curation = CurationResult(
        relevant=True,
        relevance_score=100,
        headline="Fofura para decorar seu cantinho ✿",
        description="Figura decorativa do Cinnamoroll em estilo kawaii.",
        reason="Personagem alinhado à marca.",
        category="general",
    )

    message = compose_message(item, curation)

    assert "⋆｡°✩ achadinho ✩°｡⋆" in message
    assert "achadinho tech" not in message


def test_classifies_setup_before_character_theme() -> None:
    item = product(title="Teclado mecânico Hello Kitty com keycaps PBT")

    assert classify_content_bucket(item) == "setup"


def test_editorial_rotation_prioritizes_setup_over_bigger_sanrio_discount() -> None:
    setup = product(
        product_id="setup",
        title="Mouse sem fio para computador",
        price=Decimal("90"),
        original_price=Decimal("100"),
    )
    sanrio = product(
        product_id="sanrio",
        title="Mini Figure Sanrio Cinnamoroll",
        price=Decimal("20"),
        original_price=Decimal("100"),
    )

    ordered = order_for_editorial_rotation([sanrio, setup], 20, rotation_index=0)

    assert ordered[0].product_id == "setup"


def test_anime_rotation_prefers_action_figure_over_small_standee() -> None:
    action_figure = product(
        product_id="miku",
        title="Hatsune Miku Action Figure Vocaloid 25cm",
        price=Decimal("180"),
        original_price=Decimal("200"),
    )
    standee = product(
        product_id="standee",
        title="Anime standee acrílico Project Sekai",
        price=Decimal("15"),
        original_price=Decimal("100"),
    )

    ordered = order_for_editorial_rotation(
        [standee, action_figure], 20, rotation_index=3
    )

    assert ordered[0].product_id == "miku"
