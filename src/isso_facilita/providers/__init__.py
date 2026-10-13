from isso_facilita.config import Settings
from isso_facilita.providers.aliexpress import AliExpressProvider
from isso_facilita.providers.base import MarketplaceProvider
from isso_facilita.providers.demo import DemoProvider
from isso_facilita.providers.shopee import ShopeeProvider


def build_providers(settings: Settings) -> list[MarketplaceProvider]:
    providers: list[MarketplaceProvider] = []
    for name in settings.marketplace_names:
        if name == "demo":
            providers.append(DemoProvider())
        elif name == "shopee":
            providers.append(ShopeeProvider(settings))
        elif name == "aliexpress":
            providers.append(AliExpressProvider(settings))
        else:
            raise ValueError(f"Marketplace não suportado: {name}")
    return providers


__all__ = ["MarketplaceProvider", "build_providers"]
