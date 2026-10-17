import json
from decimal import Decimal

import httpx
import pytest

from isso_facilita.curation import (
    CurationError,
    CurationResult,
    OllamaCurator,
    OpenAICurator,
    _parse_ollama_result,
    _validate_copy,
)
from isso_facilita.models import Product


def product() -> Product:
    return Product(
        marketplace="aliexpress",
        product_id="42",
        title="Fones de ouvido Bluetooth sem fio com gancho ajustável",
        product_url="https://example.com/product",
        affiliate_url="https://s.click.aliexpress.com/e/_short",
        image_url="https://example.com/image.jpg",
        price=Decimal("132.59"),
        original_price=Decimal("239.00"),
    )


def identity_file(tmp_path):
    path = tmp_path / "identity.json"
    path.write_text(
        json.dumps({"brand_name": "Isso Facilita", "voice": ["amigável"]}),
        encoding="utf-8",
    )
    return path


@pytest.mark.asyncio
async def test_curator_returns_structured_copy_without_sending_commercial_fields(
    tmp_path,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["model"] == "gpt-6-luna"
        assert "132.59" not in payload["input"]
        assert "_short" not in payload["input"]
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "relevant": True,
                                        "relevance_score": 94,
                                        "headline": "Seu som, do seu jeito ✦",
                                        "description": (
                                            "Um achadinho sem fio para acompanhar sua rotina."
                                        ),
                                        "reason": "Produto útil e alinhado à página.",
                                        "category": "tech",
                                    }
                                ),
                            }
                        ],
                    }
                ]
            },
        )

    curator = OpenAICurator(
        api_key="test-key",
        model="gpt-6-luna",
        identity_path=identity_file(tmp_path),
        transport=httpx.MockTransport(handler),
    )

    result = await curator.curate(product())

    assert result.relevant
    assert result.relevance_score == 94
    assert result.headline == "Seu som, do seu jeito ✦"


@pytest.mark.asyncio
async def test_curator_rejects_invented_numbers(tmp_path) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "relevant": True,
                                        "relevance_score": 90,
                                        "headline": "Bateria para 48 horas",
                                        "description": "Tecnologia para o dia a dia.",
                                        "reason": "Parece relevante.",
                                        "category": "tech",
                                    }
                                ),
                            }
                        ],
                    }
                ]
            },
        )

    curator = OpenAICurator(
        api_key="test-key",
        model="gpt-6-luna",
        identity_path=identity_file(tmp_path),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(CurationError, match="número ausente"):
        await curator.curate(product())


@pytest.mark.asyncio
async def test_ollama_curator_uses_local_structured_output(tmp_path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://127.0.0.1:11434/api/chat"
        payload = json.loads(request.content)
        assert payload["model"] == "qwen3-vl:4b"
        assert payload["stream"] is False
        assert payload["think"] is False
        assert payload["format"]["type"] == "object"
        assert "relevance_score" not in payload["format"]["properties"]
        assert payload["options"]["temperature"] == 0
        assert payload["options"]["num_ctx"] == 16384
        serialized = json.dumps(payload, ensure_ascii=False)
        assert "132.59" not in serialized
        assert "_short" not in serialized
        assert "Aparência é um diferencial" in serialized
        assert "Não repita mecanicamente o título" in serialized
        assert "A palavra 'cosplay' não descreve keycaps" in serialized
        assert "Nunca diga que uma característica está ausente" in serialized
        assert "descrição será o único texto editorial visível" in serialized
        assert "deve ser autossuficiente" in serialized
        assert "não prova conforto" in serialized
        assert "personagens de anime, Sanrio" in serialized
        assert "não precisam ter função tecnológica" in serialized
        assert "Anime, Sanrio e estética fofa são alternativas" in serialized
        assert "standee de Project Sekai" in serialized
        assert "nunca deve aparecer na copy" in serialized
        assert "produto exato" in serialized or "objeto exato" in serialized
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "relevant": True,
                            "headline": "Som prático para acompanhar sua rotina ✦",
                            "product_type": "Fones de ouvido",
                            "description": (
                                "Fones de ouvido Bluetooth com gancho ajustável."
                            ),
                            "reason": "O produto combina com a identidade da página.",
                            "category": "tech",
                        }
                    ),
                },
                "done": True,
            },
        )

    curator = OllamaCurator(
        model="qwen3-vl:4b",
        identity_path=identity_file(tmp_path),
        transport=httpx.MockTransport(handler),
    )

    result = await curator.curate(product())

    assert result.relevant
    assert result.relevance_score == 100
    assert result.headline.endswith("✦")
    assert result.description == "Fones de ouvido Bluetooth com gancho ajustável."


@pytest.mark.asyncio
async def test_ollama_curator_reports_connection_failure(tmp_path) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    curator = OllamaCurator(
        model="qwen3:4b",
        identity_path=identity_file(tmp_path),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(CurationError, match="conectar ao Ollama"):
        await curator.curate(product())


@pytest.mark.asyncio
async def test_ollama_repairs_unsupported_copy_once(tmp_path) -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        payload = json.loads(request.content)
        if calls == 1:
            content = {
                "relevant": True,
                "headline": "Fones para seu setup",
                "product_type": "Fones de ouvido",
                "description": "Fones de ouvido confortáveis para o computador.",
                "reason": "Produto de áudio.",
                "category": "tech",
            }
        else:
            assert "conforto ausente" in payload["messages"][-1]["content"]
            content = {
                "relevant": True,
                "headline": "Som sem fio para acompanhar seu ritmo ✦",
                "product_type": "Fones de ouvido",
                "description": "Fones de ouvido Bluetooth com gancho ajustável.",
                "reason": "Características presentes no título.",
                "category": "tech",
            }
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": json.dumps(content)}},
        )

    curator = OllamaCurator(
        model="qwen3:4b",
        identity_path=identity_file(tmp_path),
        transport=httpx.MockTransport(handler),
    )

    result = await curator.curate(product())

    assert calls == 2
    assert result.relevant
    assert result.description == "Fones de ouvido Bluetooth com gancho ajustável."


@pytest.mark.asyncio
async def test_ollama_rejects_copy_without_concrete_detail_after_three_attempts(
    tmp_path,
) -> None:
    calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        content = {
            "relevant": True,
            "headline": "Produto incrível para sua rotina",
            "product_type": "Fones de ouvido",
            "description": "Fones de ouvido ideal para o dia a dia",
            "reason": "Produto de áudio alinhado à página.",
            "category": "tech",
        }
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": json.dumps(content)}},
        )

    curator = OllamaCurator(
        model="qwen3-vl:2b-instruct",
        identity_path=identity_file(tmp_path),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(CurationError, match="diferencial concreto"):
        await curator.curate(product())

    assert calls == 3


@pytest.mark.asyncio
async def test_ollama_adds_missing_final_punctuation_without_retry(tmp_path) -> None:
    calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        content = {
            "relevant": True,
            "headline": "Som sem fio para acompanhar seu ritmo ✦",
            "product_type": "Fones de ouvido",
            "description": "Fones de ouvido Bluetooth com gancho ajustável",
            "reason": "Características presentes no título.",
            "category": "tech",
        }
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": json.dumps(content)}},
        )

    curator = OllamaCurator(
        model="qwen3-vl:2b-instruct",
        identity_path=identity_file(tmp_path),
        transport=httpx.MockTransport(handler),
    )

    result = await curator.curate(product())

    assert calls == 1
    assert result.description.endswith(".")


@pytest.mark.asyncio
async def test_ollama_sends_product_image_to_vision_model(tmp_path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                content=b"fake-image",
                headers={"content-type": "image/jpeg"},
            )
        payload = json.loads(request.content)
        assert payload["messages"][1]["images"]
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "relevant": True,
                            "headline": "Áudio sem fio para acompanhar seu ritmo ✦",
                            "product_type": "Fones de ouvido Bluetooth",
                            "description": (
                                "Fones de ouvido Bluetooth com gancho ajustável."
                            ),
                            "reason": "Objeto e característica confirmados.",
                            "category": "tech",
                        }
                    ),
                }
            },
        )

    curator = OllamaCurator(
        model="qwen3-vl:4b",
        identity_path=identity_file(tmp_path),
        use_product_images=True,
        transport=httpx.MockTransport(handler),
    )

    result = await curator.curate(product())

    assert result.relevant
    assert "Bluetooth" in result.description


def test_copy_uses_action_figure_instead_of_portuguese_figura() -> None:
    item = Product(
        marketplace="aliexpress",
        product_id="miku",
        title="Hatsune Miku Action Figure Vocaloid",
        product_url="https://example.com/item",
        affiliate_url="https://example.com/affiliate",
        image_url="",
        price=product().price,
        original_price=product().original_price,
    )
    result = _validate_copy(
        item,
        CurationResult(
            relevant=True,
            relevance_score=100,
            headline="Figura da Hatsune Miku para fãs de Vocaloid ✦",
            description="Figura da Hatsune Miku para completar a coleção.",
            reason="Colecionável de Vocaloid.",
            category="general",
        ),
    )

    assert "Action Figure" in result.headline
    assert "Action Figure" in result.description
    assert "Figura" not in result.description


def test_copy_normalizes_figure_de_acao_and_laptop() -> None:
    item = Product(
        marketplace="aliexpress",
        product_id="figure",
        title="Figure colecionável com suporte para laptop",
        product_url="https://example.com/item",
        affiliate_url="https://example.com/affiliate",
        image_url="",
        price=Decimal("120"),
        original_price=Decimal("150"),
    )
    result = _validate_copy(
        item,
        CurationResult(
            relevant=True,
            relevance_score=100,
            headline="Figure de Ação para decorar ao lado do laptop ✦",
            product_name="Figure de Ação",
            description="Figure de Ação colecionável com suporte para laptop.",
            reason="Colecionável alinhado.",
            category="general",
        ),
    )

    assert "Figure de Ação" not in result.headline
    assert "Action Figure" in result.headline
    assert "laptop" not in result.description.casefold()
    assert "notebook" in result.description.casefold()


@pytest.mark.parametrize(
    ("title", "product_type", "description"),
    [
        (
            "Keycap Genshin Impact Mini Figuras Artesanais de Hu Tao",
            "Keycaps artesanais de Genshin Impact",
            "Teclas personalizadas da Hu Tao para switches de eixo cruzado.",
        ),
        (
            "Genshin Impact Mousepad XXL Anime Tapete de mesa",
            "Mousepad XXL de Genshin Impact",
            "Tapete de mesa de Genshin Impact com impressão HD.",
        ),
        (
            "Genshin Impact Key Caps PBT Conjunto de 5 Chaves",
            "Conjunto de keycaps de Genshin Impact",
            "Teclas PBT de Genshin Impact para personalizar o teclado.",
        ),
    ],
)
def test_ollama_accepts_natural_names_for_same_product_object(
    title: str, product_type: str, description: str
) -> None:
    item = product()
    item = Product(
        marketplace=item.marketplace,
        product_id=item.product_id,
        title=title,
        product_url=item.product_url,
        affiliate_url=item.affiliate_url,
        image_url=item.image_url,
        price=item.price,
        original_price=item.original_price,
    )
    response = json.dumps(
        {
            "relevant": True,
            "headline": "Um detalhe bonito para personalizar o teclado ✦",
            "product_type": product_type,
            "description": description,
            "reason": "Produto alinhado ao nicho.",
            "category": "tech",
        }
    )

    result = _parse_ollama_result(item, response)

    assert result.relevant


def test_ollama_still_rejects_description_of_a_different_object() -> None:
    item = product()
    response = json.dumps(
        {
            "relevant": True,
            "headline": "Um detalhe bonito para o setup ✦",
            "product_type": "Fones de ouvido Bluetooth",
            "description": "Suporte de celular com anel de dedo.",
            "reason": "Produto alinhado ao nicho.",
            "category": "tech",
        }
    )

    with pytest.raises(CurationError, match="não nomeou claramente"):
        _parse_ollama_result(item, response)


def test_ollama_prefixes_detected_keycap_when_model_omits_object_name() -> None:
    item = product()
    item = Product(
        marketplace=item.marketplace,
        product_id=item.product_id,
        title="Neuvillette Keycaps Perfil Cherry PBT Genshin Impact",
        product_url=item.product_url,
        affiliate_url=item.affiliate_url,
        image_url=item.image_url,
        price=item.price,
        original_price=item.original_price,
    )
    response = json.dumps(
        {
            "relevant": True,
            "headline": "Neuvillette nos detalhes do teclado ✦",
            "product_type": "Mini Figures artesanais de Genshin Impact",
            "description": "Mini Figures em PBT inspiradas em Neuvillette.",
            "reason": "Produto alinhado ao nicho.",
            "category": "tech",
        }
    )

    result = _parse_ollama_result(item, response)

    assert result.product_name.startswith("Keycaps")
    assert result.description.startswith("Keycaps:")


def test_copy_rejects_kawaii_as_generic_published_word() -> None:
    with pytest.raises(CurationError, match="genérica ou proibida"):
        _validate_copy(
            product(),
            CurationResult(
                relevant=True,
                relevance_score=100,
                headline="Um acessório kawaii para sua rotina",
                description="Fones de ouvido Bluetooth com gancho ajustável.",
                reason="Produto de áudio.",
                category="tech",
            ),
        )


def test_copy_rejects_incomplete_or_repeated_description() -> None:
    with pytest.raises(CurationError, match="incompleta"):
        _validate_copy(
            product(),
            CurationResult(
                relevant=True,
                relevance_score=100,
                headline="Áudio sem fio para acompanhar seu ritmo ✦",
                product_name="Fones de ouvido",
                description="Fones de ouvido Bluetooth com gancho ajustável e",
                reason="Produto de áudio.",
                category="tech",
            ),
        )

    with pytest.raises(CurationError, match="repetiu o nome"):
        _validate_copy(
            product(),
            CurationResult(
                relevant=True,
                relevance_score=100,
                headline="Fones de ouvido ✿",
                product_name="Fones de ouvido",
                description="Fones de ouvido Bluetooth com gancho ajustável.",
                reason="Produto de áudio.",
                category="tech",
            ),
        )
