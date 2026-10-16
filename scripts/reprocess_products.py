"""Reprocessa produtos específicos sem alterar a fila editorial normal."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence

from isso_facilita.config import get_settings
from isso_facilita.models import Product
from isso_facilita.providers.aliexpress import AliExpressProvider
from isso_facilita.providers.base import MarketplaceProvider
from isso_facilita.runtime import build_service


class SelectedProductsProvider(MarketplaceProvider):
    name = "selected-products"

    def __init__(self, products: list[Product]) -> None:
        self.products = products

    async def discover(self) -> list[Product]:
        return self.products


def _targets(values: Sequence[str]) -> set[tuple[str, str]]:
    targets: set[tuple[str, str]] = set()
    for value in values:
        marketplace, separator, product_id = value.partition(":")
        if not separator or not marketplace.strip() or not product_id.strip():
            raise ValueError(f"Alvo inválido: {value}. Use marketplace:id.")
        targets.add((marketplace.strip().casefold(), product_id.strip()))
    return targets


async def _main(values: Sequence[str], aliexpress_keywords: Sequence[str]) -> int:
    targets = _targets(values)
    service = build_service(get_settings())
    target_marketplaces = {marketplace for marketplace, _ in targets}
    service.providers = [
        provider for provider in service.providers if provider.name in target_marketplaces
    ]
    discoveries = []
    discovery_names = []
    for provider in service.providers:
        if isinstance(provider, AliExpressProvider) and aliexpress_keywords:
            discoveries.extend(
                provider._discover_keyword(keyword)  # noqa: SLF001 - CLI operacional interno
                for keyword in aliexpress_keywords
            )
            discovery_names.extend(provider.name for _ in aliexpress_keywords)
        else:
            discoveries.append(provider.discover())
            discovery_names.append(provider.name)
    batches = await asyncio.gather(*discoveries, return_exceptions=True)
    discovered: dict[tuple[str, str], Product] = {}
    provider_errors: list[str] = []
    for provider_name, batch in zip(discovery_names, batches, strict=True):
        if isinstance(batch, BaseException):
            provider_errors.append(f"{provider_name}: {batch}")
            continue
        for product in batch:
            key = (product.marketplace.casefold(), product.product_id)
            if key in targets:
                discovered[key] = product

    missing = sorted(
        f"{marketplace}:{product_id}"
        for marketplace, product_id in targets - discovered.keys()
    )
    selected = [discovered[target] for target in targets if target in discovered]
    service.providers = [SelectedProductsProvider(selected)]
    service.max_offers_per_run = max(1, len(selected))
    service.max_ai_evaluations_per_run = max(1, len(selected))
    result = await service.run()
    print(
        json.dumps(
            {
                "requested": len(targets),
                "found": len(selected),
                "missing": missing,
                "provider_errors": provider_errors,
                "result": result.to_dict(),
            },
            ensure_ascii=False,
        )
    )
    return 0 if not missing and not provider_errors and result.failures == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--aliexpress-keyword",
        action="append",
        default=[],
        help="Busca específica usada para localizar um produto antigo do AliExpress.",
    )
    parser.add_argument("products", nargs="+", help="Produtos no formato marketplace:id")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_main(args.products, args.aliexpress_keyword)))


if __name__ == "__main__":
    main()
