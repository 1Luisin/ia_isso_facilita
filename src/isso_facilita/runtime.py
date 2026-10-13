from isso_facilita.config import Settings
from isso_facilita.db import PublicationRepository
from isso_facilita.providers import build_providers
from isso_facilita.publishers import build_publisher
from isso_facilita.service import PromotionService


def build_service(settings: Settings) -> PromotionService:
    return PromotionService(
        providers=build_providers(settings),
        publisher=build_publisher(settings),
        repository=PublicationRepository(settings.database_path),
        min_discount_percent=settings.min_discount_percent,
        max_offers_per_run=settings.max_offers_per_run,
        record_publications=not settings.dry_run,
    )
