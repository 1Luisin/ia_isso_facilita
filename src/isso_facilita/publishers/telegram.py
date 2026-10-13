import httpx

from isso_facilita.models import Product
from isso_facilita.publishers.base import Publisher


class TelegramPublisher(Publisher):
    destination = "telegram"

    def __init__(
        self,
        token: str,
        chat_id: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not token or not chat_id:
            raise ValueError("TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID são obrigatórios")
        self.api_url = f"https://api.telegram.org/bot{token}"
        self.chat_id = chat_id
        self.transport = transport

    async def publish(self, product: Product, message: str) -> None:
        method = "sendPhoto" if product.image_url else "sendMessage"
        payload = {"chat_id": self.chat_id}
        if product.image_url:
            payload.update({"photo": product.image_url, "caption": message})
        else:
            payload["text"] = message
        async with httpx.AsyncClient(timeout=30, transport=self.transport) as client:
            response = await client.post(f"{self.api_url}/{method}", json=payload)
            try:
                result = response.json()
            except ValueError:
                result = {}
        if response.is_error or not result.get("ok"):
            description = result.get("description", "resposta inválida")
            raise RuntimeError(
                f"Telegram rejeitou a publicação (HTTP {response.status_code}): {description}"
            )
