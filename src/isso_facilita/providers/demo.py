from decimal import Decimal

from isso_facilita.models import Product
from isso_facilita.providers.base import MarketplaceProvider


class DemoProvider(MarketplaceProvider):
    name = "demo"

    async def discover(self) -> list[Product]:
        return [
            Product(
                marketplace="shopee",
                product_id="demo-ssd-1tb",
                title="SSD NVMe 1 TB de alta velocidade",
                product_url="https://shopee.com.br/",
                affiliate_url="https://shopee.com.br/",
                image_url="https://placehold.co/800x800/png?text=SSD+1TB",
                price=Decimal("299.90"),
                original_price=Decimal("499.90"),
            ),
            Product(
                marketplace="aliexpress",
                product_id="demo-fone-bluetooth",
                title="Fone Bluetooth com cancelamento de ruído",
                product_url="https://pt.aliexpress.com/",
                affiliate_url="https://pt.aliexpress.com/",
                image_url="https://placehold.co/800x800/png?text=Fone+Bluetooth",
                price=Decimal("89.90"),
                original_price=Decimal("149.90"),
            ),
        ]
