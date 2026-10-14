import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

import httpx

from isso_facilita.config import Settings
from isso_facilita.models import Product
from isso_facilita.providers.base import MarketplaceProvider


def _decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value or 0).replace("%", ""))
    except InvalidOperation:
        return Decimal("0")


def sign_top_request(params: dict[str, str], secret: str) -> str:
    plain = secret + "".join(f"{key}{params[key]}" for key in sorted(params)) + secret
    return hashlib.md5(plain.encode()).hexdigest().upper()  # noqa: S324 - protocolo legado exige MD5


class AliExpressProvider(MarketplaceProvider):
    name = "aliexpress"

    def __init__(self, settings: Settings) -> None:
        required = (
            settings.aliexpress_app_key,
            settings.aliexpress_app_secret,
            settings.aliexpress_tracking_id,
        )
        if not all(required):
            raise ValueError(
                "ALIEXPRESS_APP_KEY, ALIEXPRESS_APP_SECRET e "
                "ALIEXPRESS_TRACKING_ID são obrigatórios"
            )
        self.app_key = settings.aliexpress_app_key
        self.secret = settings.aliexpress_app_secret
        self.tracking_id = settings.aliexpress_tracking_id
        self.api_url = settings.aliexpress_api_url
        self.keywords = [
            keyword.strip()
            for keyword in settings.aliexpress_keywords.split(",")
            if keyword.strip()
        ]

    async def discover(self) -> list[Product]:
        batches = await asyncio.gather(
            *(self._discover_keyword(keyword) for keyword in self.keywords)
        )
        unique: dict[str, Product] = {}
        for batch in batches:
            for product in batch:
                unique[product.product_id] = product
        return list(unique.values())

    async def _discover_keyword(self, keyword: str) -> list[Product]:
        timestamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
        params = {
            "app_key": self.app_key,
            "fields": (
                "product_id,product_title,product_main_image_url,product_detail_url,"
                "promotion_link,target_sale_price,target_original_price,target_sale_price_currency"
            ),
            "format": "json",
            "method": "aliexpress.affiliate.hotproduct.query",
            "keywords": keyword,
            "page_no": "1",
            "page_size": "20",
            "ship_to_country": "BR",
            "sign_method": "md5",
            "target_currency": "BRL",
            "target_language": "PT",
            "timestamp": timestamp,
            "tracking_id": self.tracking_id,
            "v": "2.0",
        }
        params["sign"] = sign_top_request(params, self.secret)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(self.api_url, data=params)
            response.raise_for_status()
            payload = response.json()
        if error := payload.get("error_response"):
            code = error.get("sub_code") or error.get("code") or "desconhecido"
            message = error.get("sub_msg") or error.get("msg") or "erro não informado"
            raise RuntimeError(f"AliExpress rejeitou a consulta ({code}): {message}")
        response_key = next(
            (key for key in payload if key.endswith("_response") and key != "error_response"),
            "",
        )
        if not response_key:
            raise RuntimeError("AliExpress retornou uma resposta sem dados reconhecíveis")
        envelope = payload.get(response_key, {}).get("resp_result", {})
        if str(envelope.get("resp_code", "200")) != "200":
            raise RuntimeError(f"AliExpress rejeitou a consulta: {envelope}")
        result = envelope.get("result", {})
        raw_products = result.get("products", {}).get("product", []) or []
        return [self._to_product(item) for item in raw_products]

    def _to_product(self, item: dict[str, object]) -> Product:
        price = _decimal(item.get("target_sale_price") or item.get("sale_price"))
        original = _decimal(item.get("target_original_price") or item.get("original_price"))
        return Product(
            marketplace=self.name,
            product_id=str(item.get("product_id", "")),
            title=str(item.get("product_title", "")),
            product_url=str(item.get("product_detail_url", "")),
            affiliate_url=str(item.get("promotion_link", "")),
            image_url=str(item.get("product_main_image_url", "")),
            price=price,
            original_price=original,
            currency=str(item.get("target_sale_price_currency") or "BRL"),
        )
