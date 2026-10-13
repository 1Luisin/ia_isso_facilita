from isso_facilita.config import Settings
from isso_facilita.publishers.base import Publisher
from isso_facilita.publishers.console import ConsolePublisher
from isso_facilita.publishers.telegram import TelegramPublisher
from isso_facilita.publishers.webhook import WebhookPublisher
from isso_facilita.publishers.whatsapp import WhatsAppPublisher


def build_publisher(settings: Settings) -> Publisher:
    if settings.dry_run or settings.publisher == "console":
        return ConsolePublisher()
    if settings.publisher == "telegram":
        return TelegramPublisher(settings.telegram_bot_token, settings.telegram_chat_id)
    if settings.publisher == "whatsapp":
        return WhatsAppPublisher(
            access_token=settings.whatsapp_access_token,
            phone_number_id=settings.whatsapp_phone_number_id,
            group_id=settings.whatsapp_group_id,
            api_version=settings.whatsapp_graph_api_version,
        )
    if settings.publisher == "webhook":
        return WebhookPublisher(settings.webhook_url, settings.webhook_bearer_token)
    raise ValueError(f"Publicador não suportado: {settings.publisher}")


__all__ = ["Publisher", "build_publisher"]
