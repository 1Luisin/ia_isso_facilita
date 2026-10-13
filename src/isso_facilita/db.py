import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from isso_facilita.models import Publication


class PublicationRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS publications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint TEXT NOT NULL UNIQUE,
                    marketplace TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    price TEXT NOT NULL,
                    affiliate_url TEXT NOT NULL,
                    message TEXT NOT NULL,
                    published_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def contains(self, fingerprint: str) -> bool:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT 1 FROM publications WHERE fingerprint = ?", (fingerprint,)
            ).fetchone()
        return row is not None

    def add(self, item: Publication) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO publications
                (fingerprint, marketplace, product_id, title, price, affiliate_url, message)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.fingerprint,
                    item.marketplace,
                    item.product_id,
                    item.title,
                    str(item.price),
                    item.affiliate_url,
                    item.message,
                ),
            )

    def recent(self, limit: int = 50) -> list[dict[str, object]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM publications ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]
