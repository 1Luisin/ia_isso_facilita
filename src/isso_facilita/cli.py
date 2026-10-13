import argparse
import asyncio
import json
import logging

from isso_facilita.config import get_settings
from isso_facilita.runtime import build_service


def main() -> None:
    parser = argparse.ArgumentParser(description="Bot de promoções Isso Facilita")
    parser.add_argument("command", choices=["run-once"], help="Executa uma busca imediatamente")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.command == "run-once":
        result = asyncio.run(build_service(get_settings()).run())
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
