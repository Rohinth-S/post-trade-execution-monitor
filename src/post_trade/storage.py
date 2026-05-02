"""Idempotent SQLite ingest and a transactionally consistent replay view."""

from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
import sqlite3

from .events import ExecutionBatch, Order, Receipt

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    venue TEXT NOT NULL,
    record_id TEXT NOT NULL,
    event_time TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (venue, record_id)
);
CREATE TABLE IF NOT EXISTS fills (
    venue TEXT NOT NULL,
    record_id TEXT NOT NULL,
    event_time TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (venue, record_id)
);
CREATE INDEX IF NOT EXISTS orders_by_time ON orders(event_time);
CREATE INDEX IF NOT EXISTS fills_by_time ON fills(event_time);
"""


class RecordConflict(ValueError):
    """The source reused an immutable event identity with different data."""


def _event_time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("replay cutoff must include a timezone")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


class LedgerStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, 1}:
                raise ValueError(f"unsupported ledger schema version {version}")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(f"BEGIN IMMEDIATE; {SCHEMA} PRAGMA user_version = 1; COMMIT;")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=15)

    def ingest(self, batch: ExecutionBatch) -> dict[str, int]:
        groups = (
            ("orders", ((r.venue, r.order_id, r.sent_at, r) for r in batch.orders)),
            ("fills", ((r.venue, r.fill_id, r.filled_at, r) for r in batch.fills)),
        )
        result = {"inserted_orders": 0, "inserted_fills": 0, "idempotent_retries": 0}
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            for table, records in groups:
                for venue, record_id, event_time, record in records:
                    payload = record.model_dump_json()
                    cursor = connection.execute(
                        f"INSERT INTO {table} VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
                        (venue, record_id, _event_time(event_time), payload),
                    )
                    if cursor.rowcount:
                        result[f"inserted_{table}"] += 1
                        continue
                    stored = connection.execute(
                        f"SELECT payload FROM {table} WHERE venue = ? AND record_id = ?",
                        (venue, record_id),
                    ).fetchone()[0]
                    if stored != payload:
                        raise RecordConflict(f"{table} identity {venue}/{record_id} has a different payload")
                    result["idempotent_retries"] += 1
        return result

    def statistics(self) -> dict:
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN")
            tables = {}
            for table in ("orders", "fills"):
                count, oldest, newest = connection.execute(
                    f"SELECT count(*), min(event_time), max(event_time) FROM {table}",
                ).fetchone()
                tables[table] = {"count": count, "first_event": oldest, "last_event": newest}
            return {"schema_version": connection.execute("PRAGMA user_version").fetchone()[0], **tables}

    def snapshot(self, as_of: datetime | None = None) -> ExecutionBatch:
        cutoff = _event_time(as_of) if as_of else None
        condition = "WHERE event_time <= ?" if cutoff is not None else ""
        parameters = (cutoff,) if cutoff is not None else ()
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN")
            groups = {}
            for table, model in (("orders", Order), ("fills", Receipt)):
                rows = connection.execute(
                    f"SELECT payload FROM {table} {condition} ORDER BY event_time, venue, record_id",
                    parameters,
                )
                groups[table] = [model.model_validate_json(row[0]) for row in rows]
        return ExecutionBatch.model_construct(**groups)
