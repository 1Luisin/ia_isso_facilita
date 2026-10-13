from abc import ABC, abstractmethod

from isso_facilita.models import Product


class Publisher(ABC):
    destination = "publisher"

    def destinations(self) -> list["Publisher"]:
        return [self]

    @abstractmethod
    async def publish(self, product: Product, message: str) -> None:
        """Publica uma oferta ou levanta uma exceção."""


class MultiPublisher(Publisher):
    """Agrupa destinos; o serviço publica e registra cada um separadamente."""

    destination = "multi"

    def __init__(self, publishers: list[Publisher]) -> None:
        if not publishers:
            raise ValueError("Informe pelo menos um publicador")
        self.publishers = publishers

    def destinations(self) -> list[Publisher]:
        return self.publishers

    async def publish(self, product: Product, message: str) -> None:
        raise RuntimeError("MultiPublisher deve ser expandido pelo PromotionService")
