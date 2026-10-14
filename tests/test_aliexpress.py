from decimal import Decimal

import httpx
import pytest

from isso_facilita.config import Settings
from isso_facilita.providers.aliexpress import AliExpressProvider


def settings() -> Settings:
    return Settings(
        _env_file=None,
        aliexpress_app_key="app-key",
        aliexpress_app_secret="app-secret",
        aliexpress_tracking_id="tracking-id",
        aliexpress_api_url="https://api-sg.aliexpress.com/sync",
    )


@pytest.mark.asyncio
async def test_reports_top_level_api_error(monkeypatch) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "error_response": {
                    "code": 29,
                    "msg": "Invalid app Key",
                    "sub_code": "isv.appkey-not-exists",
                }
            },
        )

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_client(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    )

    with pytest.raises(RuntimeError) as error:
        await AliExpressProvider(settings()).discover()

    assert "isv.appkey-not-exists" in str(error.value)
    assert "app-secret" not in str(error.value)


@pytest.mark.asyncio
async def test_parses_products_with_affiliate_links(monkeypatch) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "aliexpress_affiliate_hotproduct_query_response": {
                    "resp_result": {
                        "resp_code": 200,
                        "resp_msg": "success",
                        "result": {
                            "products": {
                                "product": [
                                    {
                                        "product_id": "42",
                                        "product_title": "SSD NVMe",
                                        "product_main_image_url": "https://example.com/image.jpg",
                                        "product_detail_url": "https://example.com/product",
                                        "promotion_link": "https://example.com/affiliate",
                                        "target_sale_price": "100.00",
                                        "target_original_price": "200.00",
                                        "target_sale_price_currency": "BRL",
                                    }
                                ]
                            }
                        },
                    }
                }
            },
        )

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_client(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    )

    products = await AliExpressProvider(settings()).discover()

    assert len(products) == 1
    assert products[0].price == Decimal("100.00")
    assert products[0].affiliate_url == "https://example.com/affiliate"
