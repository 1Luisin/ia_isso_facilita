import asyncio
import logging
import unicodedata
from dataclasses import asdict, dataclass
from decimal import Decimal

from isso_facilita.db import PublicationRepository
from isso_facilita.models import Product, Publication
from isso_facilita.providers.base import MarketplaceProvider
from isso_facilita.publishers.base import Publisher

logger = logging.getLogger(__name__)

TECH_KEYWORDS = {
    "ssd",
    "notebook",
    "laptop",
    "computador",
    "pc gamer",
    "monitor",
    "teclado",
    "mouse",
    "headset",
    "fone",
    "earphone",
    "earphones",
    "headphone",
    "headphones",
    "bluetooth",
    "smartphone",
    "celular",
    "tablet",
    "smartwatch",
    "smart watch",
    "roteador",
    "wifi",
    "wi-fi",
    "carregador",
    "charger",
    "power bank",
    "memoria ram",
    "placa de video",
    "gpu",
    "webcam",
    "microfone",
    "console",
    "controle",
    "hd externo",
    "pendrive",
}


def normalize(text: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(char)
    )


def is_technology(product: Product) -> bool:
    title = normalize(product.title)
    return any(keyword in title for keyword in TECH_KEYWORDS)


def format_money(value: Decimal, currency: str) -> str:
    if currency.upper() == "BRL":
        formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {formatted}"
    return f"{currency.upper()} {value:.2f}"


def compose_message(product: Product) -> str:
    marketplace = product.marketplace.title()
    discount = round(product.discount_percent)
    old_price = format_money(product.original_price, product.currency)
    price = format_money(product.price, product.currency)
    return (
        f"🔥 OFERTA DE TECNOLOGIA — {marketplace}\n\n"
        f"{product.title}\n\n"
        f"De {old_price} por {price} ({discount}% OFF)\n\n"
        f"🛒 Confira a oferta: {product.affiliate_url}\n\n"
        "⚠️ Preço e estoque podem mudar a qualquer momento. "
        "Este é um link de afiliado: podemos receber uma comissão sem custo extra para você."
    )


@dataclass(slots=True)
class RunResult:
    discovered: int = 0
    eligible: int = 0
    published: int = 0
    duplicates: int = 0
    failures: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


class PromotionService:
    def __init__(
        self,
        providers: list[MarketplaceProvider],
        publisher: Publisher,
        repository: PublicationRepository,
        min_discount_percent: float,
        max_offers_per_run: int,
        record_publications: bool = True,
    ) -> None:
        self.providers = providers
        self.publisher = publisher
        self.repository = repository
        self.min_discount_percent = min_discount_percent
        self.max_offers_per_run = max_offers_per_run
        self.record_publications = record_publications
        self._run_lock = asyncio.Lock()

    async def run(self) -> RunResult:
        async with self._run_lock:
            result = RunResult()
            batches = await asyncio.gather(
                *(provider.discover() for provider in self.providers), return_exceptions=True
            )
            products: list[Product] = []
            for provider, batch in zip(self.providers, batches, strict=True):
                if isinstance(batch, BaseException):
                    result.failures += 1
                    logger.exception("Falha ao consultar %s", provider.name, exc_info=batch)
                else:
                    products.extend(batch)
            result.discovered = len(products)
            eligible = [
                product
                for product in products
                if product.product_id
                and product.affiliate_url
                and product.price > 0
                and is_technology(product)
                and product.discount_percent >= self.min_discount_percent
            ]
            eligible.sort(key=lambda item: item.discount_percent, reverse=True)
            result.eligible = len(eligible)
            destinations = self.publisher.destinations()
            for product in eligible:
                if result.published >= self.max_offers_per_run:
                    break
                pending = (
                    destinations
                    if not self.record_publications
                    else [
                        publisher
                        for publisher in destinations
                        if not self.repository.delivered_to(
                            product.fingerprint, publisher.destination
                        )
                    ]
                )
                if not pending:
                    result.duplicates += 1
                    continue
                message = compose_message(product)
                successful = 0
                for publisher in pending:
                    try:
                        await publisher.publish(product, message)
                    except Exception:
                        result.failures += 1
                        logger.exception(
                            "Falha ao publicar %s:%s em %s",
                            product.marketplace,
                            product.product_id,
                            publisher.destination,
                        )
                        continue
                    successful += 1
                    if self.record_publications:
                        self.repository.record_delivery(
                            product.fingerprint, publisher.destination
                        )
                if successful and self.record_publications:
                    self.repository.add(
                        Publication(
                            fingerprint=product.fingerprint,
                            marketplace=product.marketplace,
                            product_id=product.product_id,
                            title=product.title,
                            price=product.price,
                            affiliate_url=product.affiliate_url,
                            message=message,
                        )
                    )
                if successful:
                    result.published += 1
            return result
