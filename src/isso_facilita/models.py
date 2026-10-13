from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Product:
    marketplace: str
    product_id: str
    title: str
    product_url: str
    image_url: str
    price: Decimal
    original_price: Decimal
    currency: str = "BRL"
    affiliate_url: str = ""

    @property
    def discount_percent(self) -> float:
        if self.original_price <= 0 or self.price >= self.original_price:
            return 0.0
        return float((self.original_price - self.price) / self.original_price * 100)

    @property
    def fingerprint(self) -> str:
        return f"{self.marketplace}:{self.product_id}:{self.price:.2f}"


@dataclass(frozen=True, slots=True)
class Publication:
    fingerprint: str
    marketplace: str
    product_id: str
    title: str
    price: Decimal
    affiliate_url: str
    message: str
