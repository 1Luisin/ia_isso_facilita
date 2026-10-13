from abc import ABC, abstractmethod

from isso_facilita.models import Product


class MarketplaceProvider(ABC):
    name: str

    @abstractmethod
    async def discover(self) -> list[Product]:
        """Retorna produtos promocionais já acompanhados por seu link de afiliado."""
