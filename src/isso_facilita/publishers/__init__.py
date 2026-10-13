from isso_facilita.config import Settings
from isso_facilita.publishers.base import MultiPublisher, Publisher
from isso_facilita.publishers.console import ConsolePublisher
from isso_facilita.publishers.telegram import TelegramPublisher
from isso_facilita.publishers.webhook import WebhookPublisher
from isso_facilita.publishers.whatsapp import WhatsAppPublisher
from isso_facilita.publishers.whatsapp_web import WhatsAppWebPublisher


def build_publisher(settings: Settings) -> Publisher:
    if settings.dry_run:
        return ConsolePublisher()
    publishers = [_build_single_publisher(settings, name) for name in settings.publisher_names]
    return publishers[0] if len(publishers) == 1 else MultiPublisher(publishers)


def _build_single_publisher(settings: Settings, name: str) -> Publisher:
    if name == "console":
        return ConsolePublisher()
    if name == "telegram":
        return TelegramPublisher(settings.telegram_bot_token, settings.telegram_chat_id)
    if name == "whatsapp":
        return WhatsAppPublisher(
            access_token=settings.whatsapp_access_token,
            phone_number_id=settings.whatsapp_phone_number_id,
            group_id=settings.whatsapp_group_id,
            api_version=settings.whatsapp_graph_api_version,
        )
    if name == "whatsapp_web":
        return WhatsAppWebPublisher(
            bridge_url=settings.whatsapp_web_bridge_url,
            token=settings.whatsapp_web_bridge_token,
            group_id=settings.whatsapp_web_group_id,
        )
    if name == "webhook":
        return WebhookPublisher(settings.webhook_url, settings.webhook_bearer_token)
    raise ValueError(f"Publicador não suportado: {name}")


__all__ = ["Publisher", "build_publisher"]
