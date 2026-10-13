import httpx

from isso_facilita.models import Product
from isso_facilita.publishers.base import Publisher


class WhatsAppWebPublisher(Publisher):
    """Envia ofertas ao serviço local conectado ao WhatsApp Web."""

    destination = "whatsapp_web"

    def __init__(
        self,
        bridge_url: str,
        token: str,
        group_id: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not bridge_url or not token:
            raise ValueError(
                "WHATSAPP_WEB_BRIDGE_URL e WHATSAPP_WEB_BRIDGE_TOKEN são obrigatórios"
            )
        self.url = f"{bridge_url.rstrip('/')}/send"
        self.token = token
        self.group_id = group_id
        self.transport = transport

    async def publish(self, product: Product, message: str) -> None:
        payload = {
            "text": message,
            "image_url": product.image_url,
            "group_id": self.group_id,
        }
        headers = {"Authorization": f"Bearer {self.token}"}
        async with httpx.AsyncClient(timeout=60, transport=self.transport) as client:
            response = await client.post(self.url, json=payload, headers=headers)
            try:
                result = response.json()
            except ValueError:
                result = {}
        if response.is_error or not result.get("ok"):
            detail = result.get("error", "resposta inválida")
            raise RuntimeError(
                f"Ponte local do WhatsApp rejeitou a publicação "
                f"(HTTP {response.status_code}): {detail}"
            )
