import asyncio
import logging
import re
import unicodedata
from collections.abc import Callable
from dataclasses import asdict, dataclass
from decimal import Decimal

from isso_facilita.curation import CurationResult, ProductCurator
from isso_facilita.db import PublicationRepository
from isso_facilita.models import Product, Publication
from isso_facilita.providers.base import MarketplaceProvider
from isso_facilita.publishers.base import Publisher

logger = logging.getLogger(__name__)

AiDecisionRecorder = Callable[[Product, CurationResult | None, bool | None, int, str], None]

TECH_KEYWORDS = {
    "ssd",
    "notebook",
    "laptop",
    "computador",
    "pc gamer",
    "monitor",
    "teclado",
    "keyboard",
    "keycap",
    "keycaps",
    "mouse",
    "mousepad",
    "deskmat",
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
    "microphone",
    "console",
    "controle",
    "controle gamer",
    "controller",
    "gaming controller",
    "gamepad",
    "kit de limpeza",
    "keyboard cleaning kit",
    "suporte para celular",
    "phone stand",
    "blocos de montar",
    "building blocks",
    "hd externo",
    "pendrive",
}

CHARACTER_AND_DECOR_KEYWORDS = {
    "action figure",
    "anime",
    "boneco",
    "boneca",
    "chibi",
    "cinnamoroll",
    "decoracao",
    "estatua",
    "figure",
    "figura",
    "fofo",
    "hello kitty",
    "kawaii",
    "keroppi",
    "kuromi",
    "mascote",
    "miniatura",
    "my melody",
    "ornamento",
    "pelucia",
    "pochacco",
    "pompompurin",
    "sanrio",
}

SETUP_KEYWORDS = {
    "apoio de pulso",
    "braco de monitor",
    "deskmat",
    "hub usb",
    "keycap",
    "keycaps",
    "laptop stand",
    "light bar",
    "luminaria de monitor",
    "microfone",
    "monitor",
    "mouse",
    "mousepad",
    "mouse pad",
    "organizador de cabo",
    "suporte de monitor",
    "suporte para notebook",
    "teclado",
    "webcam",
}

ANIME_AND_VOCALOID_KEYWORDS = {
    "anime",
    "apothecary diaries",
    "chainsaw man",
    "dan da dan",
    "dandadan",
    "demon slayer",
    "dragon ball",
    "evangelion",
    "frieren",
    "gachiakuta",
    "genshin",
    "hatsune miku",
    "jujutsu kaisen",
    "kaiju no 8",
    "kusuriya no hitorigoto",
    "miku",
    "my hero academia",
    "naruto",
    "one piece",
    "project sekai",
    "re zero",
    "solo leveling",
    "spy x family",
    "vocaloid",
}

SANRIO_KEYWORDS = {
    "cinnamoroll",
    "hello kitty",
    "keroppi",
    "kuromi",
    "my melody",
    "pochacco",
    "pompompurin",
    "sanrio",
}

COLLECTIBLE_KEYWORDS = {
    "action figure",
    "boneco",
    "boneca",
    "estatua",
    "figure",
    "figura",
    "miniatura",
    "standee",
}

# O foco editorial é setup/tecnologia. Colecionáveis entram de forma planejada,
# sem dominar a sequência só porque aparecem com desconto percentual maior.
EDITORIAL_ROTATION = (
    "setup",
    "technology",
    "setup",
    "anime_collectible",
    "setup",
    "technology",
    "setup",
    "character_collectible",
)

NON_TECH_KEYWORDS = {
    "baralho",
    "board game",
    "jogo de mesa",
    "oracle",
    "tarot",
}

HARD_REJECT_KEYWORDS = {
    "mini pc",
    "minipc",
    "desktop computer",
    "computador completo",
    "gaming pc desktop",
    "pc gamer completo",
    "all in one computer",
    "computador all in one",
    "raspberry pi",
    "compute module",
    "placa de expansao",
    "expansion board",
    "expansion card",
    "pcie switch",
    "gpu server",
    "server board",
    "backplane",
    "blood pressure",
    "pressao arterial",
    "monitor de pressao",
    "manguito de pressao",
    "sphygmomanometer",
    "nibp cuff",
    "microfone uhf",
    "microfone sem fio uhf",
    "uhf microphone",
    "wireless uhf microphone",
    "dual channel microphone",
    "microfone karaoke",
    "meias de cosplay",
    "cosplay socks",
    "kit de pintura a oleo",
    "oil painting kit",
    "placa de extensao",
    "cabo de extensao",
    "extension board",
    "extension cable",
    "power strip",
}

PREFERRED_PRODUCT_KEYWORDS = {
    "keycap",
    "keycaps",
    "deskmat",
    "mousepad",
    "mouse pad",
    "teclado mecanico",
    "mechanical keyboard",
    "rapid trigger",
    "mouse gamer",
    "gaming mouse",
    "controle gamer",
    "gaming controller",
    "gamepad",
    "light bar",
    "kit de limpeza",
    "keyboard cleaning kit",
}

LOW_PRIORITY_KEYWORDS = {
    "carregador",
    "charger",
    "capa para airpods",
    "airpods case",
    "naruto",
    "dragon ball",
}


def normalize(text: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(char)
    )


def is_technology(product: Product) -> bool:
    title = normalize(product.title)
    if any(keyword in title for keyword in NON_TECH_KEYWORDS):
        return False
    accepted_keywords = TECH_KEYWORDS | CHARACTER_AND_DECOR_KEYWORDS
    return any(
        re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", title)
        for keyword in accepted_keywords
    )


def is_hard_rejected(product: Product, max_product_price_brl: float = 500) -> bool:
    title = normalize(product.title)
    if product.currency.upper() == "BRL" and product.price > Decimal(
        str(max_product_price_brl)
    ):
        return True
    return _contains_keyword(title, HARD_REJECT_KEYWORDS)


def is_technology_category(product: Product) -> bool:
    return classify_content_bucket(product) in {"setup", "technology"}


def _contains_keyword(title: str, keywords: set[str]) -> bool:
    return any(
        re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", title)
        for keyword in keywords
    )


def classify_content_bucket(product: Product) -> str:
    title = normalize(product.title)
    if _contains_keyword(title, SETUP_KEYWORDS):
        return "setup"
    if _contains_keyword(title, COLLECTIBLE_KEYWORDS) and _contains_keyword(
        title, ANIME_AND_VOCALOID_KEYWORDS
    ):
        return "anime_collectible"
    if _contains_keyword(title, SANRIO_KEYWORDS):
        return "character_collectible"
    if _contains_keyword(title, TECH_KEYWORDS):
        return "technology"
    if _contains_keyword(title, CHARACTER_AND_DECOR_KEYWORDS):
        return "character_collectible"
    return "other"


def _character_priority(
    title: str, character_priorities: dict[str, float] | None
) -> float:
    if not character_priorities:
        return 0.0
    return max(
        (
            weight
            for keyword, weight in character_priorities.items()
            if re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", title)
        ),
        default=0.0,
    )


def _product_priority(
    product: Product, character_priorities: dict[str, float] | None = None
) -> tuple[float, float]:
    title = normalize(product.title)
    specificity = _character_priority(title, character_priorities)
    if "action figure" in title or "estatua" in title:
        specificity += 25
    if "vocaloid" in title or "hatsune miku" in title:
        specificity += 15
    if re.search(r"(?:2[0-9]|3[0-9]|40)\s*cm", title):
        specificity += 20
    if any(term in title for term in ("mecanico", "hot-swap", "pbt", "nvme", "gan")):
        specificity += 15
    if _contains_keyword(title, PREFERRED_PRODUCT_KEYWORDS):
        specificity += 30
    if _contains_keyword(title, LOW_PRIORITY_KEYWORDS):
        specificity -= 20
    if product.currency.upper() == "BRL":
        if product.price <= Decimal("150"):
            specificity += 15
        elif product.price <= Decimal("300"):
            specificity += 8
    if any(term in title for term in ("gashapon", "chaveiro", "acrilico", "standee")):
        specificity -= 15
    return specificity, product.discount_percent


def _interleave_prices(
    products: list[Product],
    minimum_discount: float,
    character_priorities: dict[str, float] | None = None,
) -> list[Product]:
    promotional = sorted(
        (item for item in products if item.discount_percent >= minimum_discount),
        key=lambda item: _product_priority(item, character_priorities),
        reverse=True,
    )
    regular = sorted(
        (item for item in products if item.discount_percent < minimum_discount),
        key=lambda item: _product_priority(item, character_priorities),
        reverse=True,
    )
    return [
        item
        for index in range(max(len(promotional), len(regular)))
        for item in (
            promotional[index] if index < len(promotional) else None,
            regular[index] if index < len(regular) else None,
        )
        if item is not None
    ]


def _interleave_marketplaces(products: list[Product]) -> list[Product]:
    grouped: dict[str, list[Product]] = {}
    for product in products:
        grouped.setdefault(product.marketplace, []).append(product)
    return [
        marketplace_products[index]
        for index in range(max((len(items) for items in grouped.values()), default=0))
        for marketplace_products in grouped.values()
        if index < len(marketplace_products)
    ]


def order_for_editorial_rotation(
    products: list[Product],
    minimum_discount: float,
    rotation_index: int,
    character_priorities: dict[str, float] | None = None,
) -> list[Product]:
    grouped: dict[str, list[Product]] = {}
    for product in products:
        grouped.setdefault(classify_content_bucket(product), []).append(product)

    bucket_order: list[str] = []
    for offset in range(len(EDITORIAL_ROTATION)):
        bucket = EDITORIAL_ROTATION[(rotation_index + offset) % len(EDITORIAL_ROTATION)]
        if bucket not in bucket_order:
            bucket_order.append(bucket)
    bucket_order.extend(
        bucket for bucket in grouped if bucket not in bucket_order
    )
    ordered: list[Product] = []
    for bucket in bucket_order:
        bucket_products = grouped.get(bucket, [])
        if bucket == "anime_collectible":
            # Uma Action Figure específica e maior deve vencer brindes, standees e
            # miniaturas genéricas, mesmo que estes exibam um desconto percentual maior.
            bucket_products = sorted(
                bucket_products,
                key=lambda item: _product_priority(item, character_priorities),
                reverse=True,
            )
        else:
            bucket_products = _interleave_prices(
                bucket_products, minimum_discount, character_priorities
            )
        ordered.extend(_interleave_marketplaces(bucket_products))
    return ordered


def format_money(value: Decimal, currency: str) -> str:
    if currency.upper() == "BRL":
        formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {formatted}"
    return f"{currency.upper()} {value:.2f}"


def compose_message(product: Product, curation: CurationResult | None = None) -> str:
    marketplace = product.marketplace.title()
    discount = round(product.discount_percent)
    price = format_money(product.price, product.currency)
    if product.discount_percent > 0:
        old_price = format_money(product.original_price, product.currency)
        price_block = (
            f"⊹ De: {old_price}\n"
            f"✦ Por: {price}\n"
            f"ᯓ★ Desconto: {discount}% OFF\n\n"
        )
    else:
        price_block = f"✦ Preço: {price}\n\n"
    editorial = ""
    if curation:
        editorial = f"{curation.headline}\n{curation.description}\n\n"
    is_tech = (
        curation.category == "tech" if curation else is_technology_category(product)
    )
    section_label = "achadinho tech" if is_tech else "achadinho"
    display_name = curation.product_name if curation and curation.product_name else product.title
    return (
        "✿ ISSO FACILITA ✿\n"
        f"⋆｡°✩ {section_label} ✩°｡⋆\n\n"
        f"{editorial}"
        f"𖥔 Produto: {display_name}\n\n"
        f"{price_block}"
        f"╰┈➤ Confira no {marketplace}: {product.affiliate_url}"
    )


@dataclass(slots=True)
class RunResult:
    discovered: int = 0
    eligible: int = 0
    published: int = 0
    duplicates: int = 0
    failures: int = 0
    ai_rejected: int = 0
    ai_failures: int = 0
    ai_evaluated: int = 0
    ai_paused: int = 0

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
        include_non_promotional_products: bool = True,
        record_publications: bool = True,
        curator: ProductCurator | None = None,
        ai_relevance_threshold: int = 75,
        max_ai_evaluations_per_run: int = 6,
        character_priorities: dict[str, float] | None = None,
        ai_decision_recorder: AiDecisionRecorder | None = None,
        max_product_price_brl: float = 500,
        require_ai_for_publication: bool = False,
    ) -> None:
        self.providers = providers
        self.publisher = publisher
        self.repository = repository
        self.min_discount_percent = min_discount_percent
        self.include_non_promotional_products = include_non_promotional_products
        self.max_offers_per_run = max_offers_per_run
        self.record_publications = record_publications
        self.curator = curator
        self.ai_relevance_threshold = ai_relevance_threshold
        self.max_ai_evaluations_per_run = max_ai_evaluations_per_run
        self.character_priorities = {
            normalize(keyword): weight
            for keyword, weight in (character_priorities or {}).items()
        }
        self.ai_decision_recorder = ai_decision_recorder
        self.max_product_price_brl = max_product_price_brl
        self.require_ai_for_publication = require_ai_for_publication
        self._run_lock = asyncio.Lock()

    def _record_ai_decision(
        self,
        product: Product,
        curation: CurationResult | None,
        accepted: bool | None,
        error_message: str = "",
    ) -> None:
        if not self.ai_decision_recorder:
            return
        try:
            self.ai_decision_recorder(
                product,
                curation,
                accepted,
                self.ai_relevance_threshold,
                error_message,
            )
        except Exception:
            logger.exception(
                "Falha ao registrar a decisão da IA para %s:%s",
                product.marketplace,
                product.product_id,
            )

    async def run(self) -> RunResult:
        async with self._run_lock:
            result = RunResult()
            if self.require_ai_for_publication and self.curator is None:
                result.ai_paused = 1
                logger.warning(
                    "Publicação pausada: a curadoria por IA está desativada no modo real."
                )
                return result
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
                and not is_hard_rejected(product, self.max_product_price_brl)
                and is_technology(product)
                and (
                    self.include_non_promotional_products
                    or product.discount_percent >= self.min_discount_percent
                )
            ]
            try:
                rotation_index = int(self.repository.get_state("editorial_rotation", "0"))
            except ValueError:
                rotation_index = 0
            eligible = order_for_editorial_rotation(
                eligible,
                self.min_discount_percent,
                rotation_index,
                self.character_priorities,
            )
            result.eligible = len(eligible)
            candidate_offset = 0
            if self.curator and eligible:
                try:
                    candidate_offset = int(
                        self.repository.get_state("ai_candidate_offset", "0")
                    ) % len(eligible)
                except ValueError:
                    candidate_offset = 0
                eligible = eligible[candidate_offset:] + eligible[:candidate_offset]
            next_candidate_offset = candidate_offset
            destinations = self.publisher.destinations()
            for position, product in enumerate(eligible):
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
                curation = None
                if self.curator:
                    if result.ai_evaluated >= self.max_ai_evaluations_per_run:
                        break
                    result.ai_evaluated += 1
                    next_candidate_offset = (
                        candidate_offset + position + 1
                    ) % len(eligible)
                    try:
                        curation = await self.curator.curate(product)
                    except Exception as error:
                        result.failures += 1
                        result.ai_failures += 1
                        self._record_ai_decision(product, None, None, str(error))
                        logger.exception(
                            "Falha na curadoria por IA de %s:%s",
                            product.marketplace,
                            product.product_id,
                        )
                        continue
                    accepted = (
                        curation.relevant
                        and curation.relevance_score >= self.ai_relevance_threshold
                    )
                    self._record_ai_decision(product, curation, accepted)
                    if not accepted:
                        result.ai_rejected += 1
                        continue
                message = compose_message(product, curation)
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
                    if self.record_publications:
                        self.repository.set_state(
                            "editorial_rotation",
                            str((rotation_index + 1) % len(EDITORIAL_ROTATION)),
                        )
                    rotation_index = (rotation_index + 1) % len(EDITORIAL_ROTATION)
            if self.curator and self.record_publications:
                if result.published:
                    self.repository.set_state("ai_candidate_offset", "0")
                elif result.ai_evaluated:
                    self.repository.set_state(
                        "ai_candidate_offset", str(next_candidate_offset)
                    )
            return result
