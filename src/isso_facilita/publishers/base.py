from abc import ABC, abstractmethod

from isso_facilita.models import Product


class Publisher(ABC):
    @abstractmethod
    async def publish(self, product: Product, message: str) -> None:
        """Publica uma oferta ou levanta uma exceção."""
