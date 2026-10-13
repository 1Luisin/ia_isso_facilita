import logging

from isso_facilita.models import Product
from isso_facilita.publishers.base import Publisher

logger = logging.getLogger(__name__)


class ConsolePublisher(Publisher):
    async def publish(self, product: Product, message: str) -> None:
        logger.info("SIMULAÇÃO | %s\n%s", product.image_url, message)
