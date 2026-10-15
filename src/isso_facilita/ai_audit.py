from __future__ import annotations

import json
import logging
from collections import deque
from datetime import datetime
from pathlib import Path

from isso_facilita.curation import CurationResult
from isso_facilita.models import Product

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AI_AUDIT_PATH = PROJECT_ROOT / "data" / "ai-curation.jsonl"


def record_ai_decision(
    product: Product,
    curation: CurationResult | None,
    accepted: bool | None,
    threshold: int,
    error_message: str = "",
    *,
    log_path: Path = AI_AUDIT_PATH,
) -> None:
    """Persist an AI decision without ever interrupting the publication pipeline."""
    if accepted is True:
        status = "accepted"
    elif accepted is False:
        status = "rejected"
    else:
        status = "error"

    entry: dict[str, object] = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": status,
        "marketplace": product.marketplace,
        "product_id": product.product_id,
        "title": product.title,
        "affiliate_url": product.affiliate_url,
        "score": curation.relevance_score if curation else None,
        "threshold": threshold,
        "ai_relevant": curation.relevant if curation else None,
        "reason": curation.reason if curation else error_message,
    }
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8", newline="\n") as log_file:
            log_file.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")))
            log_file.write("\n")
    except OSError:
        logger.exception("Não foi possível gravar o histórico local de decisões da IA")


def read_ai_decisions(
    log_path: Path = AI_AUDIT_PATH,
    limit: int = 300,
) -> list[dict[str, object]]:
    """Return the newest valid audit entries first, ignoring incomplete lines."""
    if not log_path.exists() or limit <= 0:
        return []

    recent: deque[dict[str, object]] = deque(maxlen=limit)
    try:
        with log_path.open(encoding="utf-8") as log_file:
            for line in log_file:
                try:
                    entry = json.loads(line)
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if isinstance(entry, dict) and entry.get("status") in {
                    "accepted",
                    "rejected",
                    "error",
                }:
                    recent.append(entry)
    except OSError:
        logger.exception("Não foi possível ler o histórico local de decisões da IA")
        return []
    return list(reversed(recent))
