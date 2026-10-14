import json
from decimal import Decimal

import httpx
import pytest

from isso_facilita.curation import CurationError, OllamaCurator, OpenAICurator
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
        assert payload["model"] == "qwen3:4b"
        assert payload["stream"] is False
        assert payload["think"] is False
        assert payload["format"]["type"] == "object"
        assert payload["options"]["temperature"] == 0
        serialized = json.dumps(payload, ensure_ascii=False)
        assert "132.59" not in serialized
        assert "_short" not in serialized
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "relevant": True,
                            "relevance_score": 92,
                            "headline": "Som prático para acompanhar sua rotina ✦",
                            "description": "Um achadinho sem fio e fácil de usar no dia a dia.",
                            "reason": "O produto combina com a identidade da página.",
                        }
                    ),
                },
                "done": True,
            },
        )

    curator = OllamaCurator(
        model="qwen3:4b",
        identity_path=identity_file(tmp_path),
        transport=httpx.MockTransport(handler),
    )

    result = await curator.curate(product())

    assert result.relevant
    assert result.relevance_score == 92
    assert result.headline.endswith("✦")


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
