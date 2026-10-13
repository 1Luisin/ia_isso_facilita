import httpx

from isso_facilita.models import Product
from isso_facilita.publishers.base import Publisher


class WebhookPublisher(Publisher):
    destination = "webhook"

    def __init__(self, url: str, bearer_token: str = "") -> None:
        if not url:
            raise ValueError("WEBHOOK_URL é obrigatório")
        self.url = url
        self.headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}

    async def publish(self, product: Product, message: str) -> None:
        payload = {
            "text": message,
            "image_url": product.image_url,
            "marketplace": product.marketplace,
            "product_id": product.product_id,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(self.url, json=payload, headers=self.headers)
            response.raise_for_status()
