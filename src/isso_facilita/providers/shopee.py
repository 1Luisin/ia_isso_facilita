import hashlib
import json
import time
from decimal import Decimal, InvalidOperation

import httpx

from isso_facilita.config import Settings
from isso_facilita.models import Product
from isso_facilita.providers.base import MarketplaceProvider

PRODUCT_QUERY = """
query ProductOffers($page: Int!, $limit: Int!) {
  productOfferV2(listType: 2, sortType: 2, page: $page, limit: $limit) {
    nodes {
      itemId
      productName
      productLink
      offerLink
      imageUrl
      priceMin
      priceMax
      priceDiscountRate
    }
  }
}
"""


def _decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except InvalidOperation:
        return Decimal("0")


class ShopeeProvider(MarketplaceProvider):
    name = "shopee"

    def __init__(self, settings: Settings) -> None:
        if not settings.shopee_app_id or not settings.shopee_secret:
            raise ValueError("SHOPEE_APP_ID e SHOPEE_SECRET são obrigatórios")
        self.app_id = settings.shopee_app_id
        self.secret = settings.shopee_secret
        self.api_url = settings.shopee_api_url

    async def discover(self) -> list[Product]:
        payload = {"query": PRODUCT_QUERY, "variables": {"page": 1, "limit": 50}}
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        timestamp = int(time.time())
        signature = hashlib.sha256(
            f"{self.app_id}{timestamp}{body}{self.secret}".encode()
        ).hexdigest()
        headers = {
            "Authorization": (
                f"SHA256 Credential={self.app_id}, Timestamp={timestamp}, Signature={signature}"
            ),
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(self.api_url, content=body.encode(), headers=headers)
            response.raise_for_status()
            result = response.json()
        if result.get("errors"):
            raise RuntimeError(f"Shopee rejeitou a consulta: {result['errors']}")
        nodes = result.get("data", {}).get("productOfferV2", {}).get("nodes", []) or []
        products: list[Product] = []
        for node in nodes:
            price = _decimal(node.get("priceMin"))
            rate = _decimal(node.get("priceDiscountRate"))
            original = price / (Decimal("1") - rate / 100) if 0 < rate < 100 else price
            products.append(
                Product(
                    marketplace=self.name,
                    product_id=str(node.get("itemId", "")),
                    title=str(node.get("productName", "")),
                    product_url=str(node.get("productLink", "")),
                    affiliate_url=str(node.get("offerLink", "")),
                    image_url=str(node.get("imageUrl", "")),
                    price=price,
                    original_price=original,
                )
            )
        return products
