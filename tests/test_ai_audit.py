from decimal import Decimal
from pathlib import Path

from isso_facilita.ai_audit import read_ai_decisions, record_ai_decision
from isso_facilita.curation import CurationResult
from isso_facilita.models import Product


def make_product(product_id: str) -> Product:
    return Product(
        marketplace="aliexpress",
        product_id=product_id,
        title=f"Teclado mecânico {product_id}",
        product_url=f"https://example.com/products/{product_id}",
        affiliate_url=f"https://example.com/affiliate/{product_id}",
        image_url="",
        price=Decimal("100"),
        original_price=Decimal("150"),
    )


def test_ai_audit_records_accepted_and_rejected_links(tmp_path: Path) -> None:
    log_path = tmp_path / "ai-curation.jsonl"
    accepted = CurationResult(
        relevant=True,
        relevance_score=91,
        headline="Um teclado para o setup",
        description="Teclado mecânico com conexão USB.",
        reason="Produto alinhado à página.",
    )
    rejected = CurationResult(
        relevant=False,
        relevance_score=18,
        headline="",
        description="",
        reason="Produto fora da identidade editorial.",
    )

    record_ai_decision(make_product("accepted"), accepted, True, 75, log_path=log_path)
    record_ai_decision(make_product("rejected"), rejected, False, 75, log_path=log_path)

    entries = read_ai_decisions(log_path)
    assert [entry["status"] for entry in entries] == ["rejected", "accepted"]
    assert entries[0]["affiliate_url"] == "https://example.com/affiliate/rejected"
    assert entries[1]["score"] == 91
    assert entries[1]["reason"] == "Produto alinhado à página."


def test_ai_audit_ignores_incomplete_lines_and_respects_limit(tmp_path: Path) -> None:
    log_path = tmp_path / "ai-curation.jsonl"
    record_ai_decision(make_product("one"), None, None, 75, "tempo esgotado", log_path=log_path)
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write("{incompleto\n")
    record_ai_decision(make_product("two"), None, None, 75, "resposta inválida", log_path=log_path)

    entries = read_ai_decisions(log_path, limit=1)
    assert len(entries) == 1
    assert entries[0]["product_id"] == "two"
    assert entries[0]["status"] == "error"


def test_ai_audit_marks_repaired_copy_and_can_deduplicate_products(tmp_path: Path) -> None:
    log_path = tmp_path / "ai-curation.jsonl"
    item = make_product("same")
    record_ai_decision(item, None, None, 75, "primeira falha", log_path=log_path)
    repaired = CurationResult(
        relevant=True,
        relevance_score=100,
        headline="",
        description="Teclado mecânico com conexão USB.",
        reason="Produto alinhado.",
        copy_repaired=True,
        repair_reason="A descrição original estava incompleta",
    )
    record_ai_decision(item, repaired, True, 75, log_path=log_path)

    entries = read_ai_decisions(log_path, unique_products=True)

    assert len(entries) == 1
    assert entries[0]["status"] == "repaired"
    assert entries[0]["repair_reason"] == "A descrição original estava incompleta"
