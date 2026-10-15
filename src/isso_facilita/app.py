import asyncio
import html
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from urllib.parse import quote

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse

from isso_facilita.config import get_settings
from isso_facilita.db import PublicationRepository
from isso_facilita.runtime import build_service
from isso_facilita.service import PromotionService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

settings = get_settings()
service = build_service(settings)
repository = PublicationRepository(settings.database_path)


async def scheduler_loop(bot: PromotionService, interval_minutes: int) -> None:
    loop = asyncio.get_running_loop()
    while True:
        started_at = loop.time()
        try:
            result = await bot.run()
            logger.info("Ciclo concluído: %s", result.to_dict())
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Falha inesperada no ciclo agendado")
        elapsed_seconds = loop.time() - started_at
        await asyncio.sleep(cycle_delay_seconds(interval_minutes, elapsed_seconds))


def cycle_delay_seconds(interval_minutes: int, elapsed_seconds: float) -> float:
    return max(0.0, interval_minutes * 60 - elapsed_seconds)


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


def render_dashboard(items: list[dict[str, object]]) -> str:
    cards: list[str] = []
    for item in items:
        message = str(item["message"])
        share_url = f"https://wa.me/?text={quote(message)}"
        title = html.escape(str(item["title"]))
        marketplace = html.escape(str(item["marketplace"]).title())
        published_at = html.escape(str(item["published_at"]))
        cards.append(
            f"""
            <article class="offer">
              <div class="meta">{marketplace} · {published_at}</div>
              <h2>{title}</h2>
              <pre>{html.escape(message)}</pre>
              <a class="share" href="{html.escape(share_url, quote=True)}"
                 target="_blank" rel="noopener noreferrer">Compartilhar no WhatsApp</a>
            </article>
            """
        )
    content = "".join(cards) or (
        '<div class="empty">Nenhuma publicação ainda. Execute uma busca para começar.</div>'
    )
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Isso Facilita — Publicações</title>
  <style>
    :root {{ color-scheme: light; font-family: system-ui, sans-serif; }}
    body {{ margin: 0; background: #f4f5f7; color: #17202a; }}
    main {{ width: min(900px, calc(100% - 32px)); margin: 40px auto; }}
    h1 {{ margin-bottom: 8px; }}
    .intro {{ color: #5d6d7e; margin: 0 0 28px; }}
    .offer {{ background: white; border-radius: 16px; padding: 24px; margin: 16px 0;
              box-shadow: 0 5px 20px rgba(0,0,0,.07); }}
    .meta {{ color: #667085; font-size: 14px; }}
    h2 {{ font-size: 20px; margin: 8px 0 16px; }}
    pre {{ white-space: pre-wrap; font: inherit; line-height: 1.5; background: #f8fafc;
           padding: 16px; border-radius: 10px; }}
    .share {{ display: inline-block; color: white; background: #128c7e; padding: 12px 18px;
              border-radius: 9px; text-decoration: none; font-weight: 700; }}
    .share:hover {{ background: #075e54; }}
    .empty {{ background: white; padding: 32px; border-radius: 16px; color: #667085; }}
  </style>
</head>
<body>
  <main>
    <h1>Isso Facilita</h1>
    <p class="intro">Ofertas publicadas no Telegram e prontas para compartilhar no WhatsApp.</p>
    {content}
  </main>
</body>
</html>"""


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
        "ai_curation": settings.ai_curation_enabled,
        "ai_provider": settings.ai_provider if settings.ai_curation_enabled else None,
        "ai_model": settings.ai_model if settings.ai_curation_enabled else None,
    }


@app.get("/", response_class=HTMLResponse)
async def dashboard(token: str | None = Query(default=None)) -> HTMLResponse:
    if settings.bot_api_token and token != settings.bot_api_token:
        raise HTTPException(status_code=401, detail="Token inválido")
    return HTMLResponse(render_dashboard(repository.recent(50)))


@app.post("/runs", dependencies=[Depends(require_token)])
async def run_now() -> dict[str, int]:
    return (await service.run()).to_dict()


@app.get("/publications", dependencies=[Depends(require_token)])
async def publications(limit: int = Query(default=50, ge=1, le=200)) -> list[dict[str, object]]:
    return repository.recent(limit)
