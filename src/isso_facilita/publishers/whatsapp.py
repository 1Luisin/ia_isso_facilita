import httpx

from isso_facilita.models import Product
from isso_facilita.publishers.base import Publisher


class WhatsAppPublisher(Publisher):
    """Publica em um grupo habilitado na WhatsApp Business Platform Groups API."""

    destination = "whatsapp"

    def __init__(
        self,
        access_token: str,
        phone_number_id: str,
        group_id: str,
        api_version: str = "v25.0",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not access_token or not phone_number_id or not group_id:
            raise ValueError(
                "WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID e "
                "WHATSAPP_GROUP_ID são obrigatórios"
            )
        version = api_version if api_version.startswith("v") else f"v{api_version}"
        self.url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
        self.group_id = group_id
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        self.transport = transport

    def build_payload(self, product: Product, message: str) -> dict[str, object]:
        common: dict[str, object] = {
            "messaging_product": "whatsapp",
            "recipient_type": "group",
            "to": self.group_id,
        }
        if product.image_url:
            return {
                **common,
                "type": "image",
                "image": {"link": product.image_url, "caption": message},
            }
        return {
            **common,
            "type": "text",
            "text": {"preview_url": True, "body": message},
        }

    async def publish(self, product: Product, message: str) -> None:
        async with httpx.AsyncClient(timeout=30, transport=self.transport) as client:
            response = await client.post(
                self.url,
                json=self.build_payload(product, message),
                headers=self.headers,
            )
            response.raise_for_status()
            result = response.json()
        if not result.get("messages"):
            raise RuntimeError(f"WhatsApp não confirmou a publicação: {result}")
