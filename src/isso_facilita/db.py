import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS publication_deliveries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    published_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(fingerprint, destination)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS app_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_failures (
                    fingerprint TEXT PRIMARY KEY,
                    failure_count INTEGER NOT NULL,
                    last_reason TEXT NOT NULL,
                    cooldown_until TEXT
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

    def delivered_to(self, fingerprint: str, destination: str) -> bool:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM publication_deliveries
                WHERE fingerprint = ? AND destination = ?
                """,
                (fingerprint, destination),
            ).fetchone()
        return row is not None

    def record_delivery(self, fingerprint: str, destination: str) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO publication_deliveries (fingerprint, destination)
                VALUES (?, ?)
                """,
                (fingerprint, destination),
            )

    def recent(self, limit: int = 50) -> list[dict[str, object]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM publications ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def get_state(self, key: str, default: str = "") -> str:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT value FROM app_state WHERE key = ?", (key,)
            ).fetchone()
        return str(row["value"]) if row else default

    def set_state(self, key: str, value: str) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO app_state (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def ai_failure_in_cooldown(
        self, fingerprint: str, *, now: datetime | None = None
    ) -> bool:
        current = now or datetime.now(UTC)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT cooldown_until FROM ai_failures WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
        if not row or not row["cooldown_until"]:
            return False
        try:
            return datetime.fromisoformat(str(row["cooldown_until"])) > current
        except ValueError:
            return False

    def record_ai_failure(
        self,
        fingerprint: str,
        reason: str,
        *,
        max_attempts: int = 3,
        cooldown_hours: int = 6,
        now: datetime | None = None,
    ) -> int:
        current = now or datetime.now(UTC)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT failure_count, cooldown_until FROM ai_failures WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
            previous_count = int(row["failure_count"]) if row else 0
            if row and row["cooldown_until"]:
                try:
                    if datetime.fromisoformat(str(row["cooldown_until"])) <= current:
                        previous_count = 0
                except ValueError:
                    previous_count = 0
            failure_count = previous_count + 1
            cooldown_until = (
                (current + timedelta(hours=cooldown_hours)).isoformat()
                if failure_count >= max_attempts
                else None
            )
            connection.execute(
                """
                INSERT INTO ai_failures
                    (fingerprint, failure_count, last_reason, cooldown_until)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(fingerprint) DO UPDATE SET
                    failure_count = excluded.failure_count,
                    last_reason = excluded.last_reason,
                    cooldown_until = excluded.cooldown_until
                """,
                (fingerprint, failure_count, reason, cooldown_until),
            )
        return failure_count

    def clear_ai_failure(self, fingerprint: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM ai_failures WHERE fingerprint = ?", (fingerprint,)
            )
