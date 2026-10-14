from isso_facilita.config import Settings
from isso_facilita.curation import OllamaCurator, OpenAICurator
from isso_facilita.db import PublicationRepository
from isso_facilita.providers import build_providers
from isso_facilita.publishers import build_publisher
from isso_facilita.service import PromotionService


def build_service(settings: Settings) -> PromotionService:
    curator = None
    if settings.ai_curation_enabled:
        if settings.ai_provider == "ollama":
            curator = OllamaCurator(
                model=settings.ollama_model,
                identity_path=settings.brand_identity_path,
                api_url=settings.ollama_api_url,
                timeout_seconds=settings.ollama_timeout_seconds,
            )
        else:
            curator = OpenAICurator(
                api_key=settings.openai_api_key,
                model=settings.openai_model,
                identity_path=settings.brand_identity_path,
                api_url=settings.openai_api_url,
                timeout_seconds=settings.openai_timeout_seconds,
            )
    return PromotionService(
        providers=build_providers(settings),
        publisher=build_publisher(settings),
        repository=PublicationRepository(settings.database_path),
        min_discount_percent=settings.min_discount_percent,
        max_offers_per_run=settings.max_offers_per_run,
        record_publications=not settings.dry_run,
        curator=curator,
        ai_relevance_threshold=settings.ai_relevance_threshold,
    )
