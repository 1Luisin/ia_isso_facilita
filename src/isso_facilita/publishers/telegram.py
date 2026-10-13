import httpx

from isso_facilita.models import Product
from isso_facilita.publishers.base import Publisher


class TelegramPublisher(Publisher):
    def __init__(self, token: str, chat_id: str) -> None:
        if not token or not chat_id:
            raise ValueError("TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID são obrigatórios")
        self.api_url = f"https://api.telegram.org/bot{token}"
        self.chat_id = chat_id

    async def publish(self, product: Product, message: str) -> None:
        method = "sendPhoto" if product.image_url else "sendMessage"
        payload = {"chat_id": self.chat_id}
        if product.image_url:
            payload.update({"photo": product.image_url, "caption": message})
        else:
            payload["text"] = message
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{self.api_url}/{method}", json=payload)
            response.raise_for_status()
            result = response.json()
        if not result.get("ok"):
            raise RuntimeError(f"Telegram rejeitou a publicação: {result}")
