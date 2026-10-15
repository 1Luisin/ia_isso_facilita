from isso_facilita.ai_audit import record_ai_decision
from isso_facilita.config import Settings
from isso_facilita.curation import OllamaCurator, OpenAICurator, load_brand_identity
from isso_facilita.db import PublicationRepository
from isso_facilita.providers import build_providers
from isso_facilita.publishers import build_publisher
from isso_facilita.service import PromotionService


def build_service(settings: Settings) -> PromotionService:
    identity = load_brand_identity(settings.brand_identity_path)
    trend_config = identity.get("character_trends", {})
    character_priorities: dict[str, float] = {}
    if isinstance(trend_config, dict):
        for field, weight in (
            ("current_characters", 75.0),
            ("current_franchises", 60.0),
            ("famous_franchises", 35.0),
        ):
            values = trend_config.get(field, [])
            if isinstance(values, list):
                character_priorities.update(
                    {str(value): weight for value in values if str(value).strip()}
                )
    curator = None
    if settings.ai_curation_enabled:
        if settings.ai_provider == "ollama":
            curator = OllamaCurator(
                model=settings.ollama_model,
                identity_path=settings.brand_identity_path,
                api_url=settings.ollama_api_url,
                timeout_seconds=settings.ollama_timeout_seconds,
                use_product_images=settings.ollama_use_product_images,
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
        include_non_promotional_products=settings.include_non_promotional_products,
        max_offers_per_run=settings.max_offers_per_run,
        record_publications=not settings.dry_run,
        curator=curator,
        ai_relevance_threshold=settings.ai_relevance_threshold,
        max_ai_evaluations_per_run=settings.max_ai_evaluations_per_run,
        character_priorities=character_priorities,
        ai_decision_recorder=record_ai_decision if curator else None,
    )
