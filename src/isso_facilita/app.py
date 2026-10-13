import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query

from isso_facilita.config import get_settings
from isso_facilita.db import PublicationRepository
from isso_facilita.runtime import build_service
from isso_facilita.service import PromotionService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

settings = get_settings()
service = build_service(settings)
repository = PublicationRepository(settings.database_path)


async def scheduler_loop(bot: PromotionService, interval_minutes: int) -> None:
    while True:
        try:
            result = await bot.run()
            logger.info("Ciclo concluído: %s", result.to_dict())
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Falha inesperada no ciclo agendado")
        await asyncio.sleep(interval_minutes * 60)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(scheduler_loop(service, settings.scan_interval_minutes))
    yield
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


app = FastAPI(
    title="Isso Facilita",
    description="Curadoria e publicação de ofertas de tecnologia com links de afiliado.",
    version="0.1.0",
    lifespan=lifespan,
)


def require_token(
    x_api_token: Annotated[str | None, Header()] = None,
) -> None:
    if settings.bot_api_token and x_api_token != settings.bot_api_token:
        raise HTTPException(status_code=401, detail="Token inválido")


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "marketplaces": settings.marketplace_names,
        "publisher": "console" if settings.dry_run else settings.publisher,
        "dry_run": settings.dry_run,
    }


@app.post("/runs", dependencies=[Depends(require_token)])
async def run_now() -> dict[str, int]:
    return (await service.run()).to_dict()


@app.get("/publications", dependencies=[Depends(require_token)])
async def publications(limit: int = Query(default=50, ge=1, le=200)) -> list[dict[str, object]]:
    return repository.recent(limit)
