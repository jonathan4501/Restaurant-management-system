"""
The bridge's durable state: a print queue and the stream cursor, in one SQLite file.

Two guarantees come from this file, and they are the whole reason it exists.

**Nothing prints twice.** `jobs.job_key` is the primary key and is derived from the event id, so it
is identical every time the same event is seen. Enqueueing is `INSERT OR IGNORE`: a reconnect that
replays an event the bridge already handled inserts nothing and prints nothing. Reconnect
de-duplication is a uniqueness constraint, not a timing window.

**Nothing is lost.** A job is written to disk before the cursor moves past its event, and a job is
only marked printed after the printer accepted the bytes. A power cut or a `systemctl restart`
therefore leaves work in the queue, and the next start prints it. A printer that is switched off
simply accumulates jobs until it answers.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_key     TEXT PRIMARY KEY,
    printer     TEXT NOT NULL,
    fetch_path  TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    payload     BLOB,
    attempts    INTEGER NOT NULL DEFAULT 0,
    last_error  TEXT,
    created_at  TEXT NOT NULL,
    printed_at  TEXT
);
CREATE INDEX IF NOT EXISTS jobs_pending_idx ON jobs (printed_at, created_at);

CREATE TABLE IF NOT EXISTS cursor (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    last_event_id TEXT
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class QueuedJob:
    job_key: str
    printer: str
    fetch_path: str
    description: str
    payload: bytes | None
    attempts: int
    last_error: str | None

    @property
    def is_materialised(self) -> bool:
        """True once the ESC/POS bytes have been fetched and stored — ready to go to a socket."""
        return self.payload is not None


class Store:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        if self.path.parent and str(self.path.parent) not in ("", "."):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        # WAL survives a power cut mid-write, which is the normal way a Pi shuts down in Accra.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.executescript(SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---------------------------------------------------------------- cursor

    def last_event_id(self) -> str | None:
        """The `Last-Event-ID` to resume the stream from, or None for a first-ever start."""
        with closing(self._conn.execute("SELECT last_event_id FROM cursor WHERE id = 1")) as cur:
            row = cur.fetchone()
        return row["last_event_id"] if row else None

    def set_last_event_id(self, value: str | int) -> None:
        """
        Called only after every job for that event is durably queued. Moving the cursor first would
        mean a crash in between silently skipped a ticket.
        """
        self._conn.execute(
            "INSERT INTO cursor (id, last_event_id) VALUES (1, ?) "
            "ON CONFLICT (id) DO UPDATE SET last_event_id = excluded.last_event_id",
            (str(value),),
        )

    # ---------------------------------------------------------------- queue

    def enqueue(
        self, *, job_key: str, printer: str, fetch_path: str, description: str = ""
    ) -> bool:
        """
        Add a job unless `job_key` is already known. Returns True when this call created it.

        False means "already seen" — which on a reconnect is the answer that stops a double print,
        and is not an error.
        """
        with closing(
            self._conn.execute(
                "INSERT OR IGNORE INTO jobs (job_key, printer, fetch_path, description, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (job_key, printer, fetch_path, description, _now()),
            )
        ) as cur:
            return cur.rowcount == 1

    def store_payload(self, job_key: str, payload: bytes) -> None:
        self._conn.execute(
            "UPDATE jobs SET payload = ? WHERE job_key = ? AND printed_at IS NULL",
            (sqlite3.Binary(payload), job_key),
        )

    def pending(self, limit: int = 100) -> list[QueuedJob]:
        """Everything still owed to a printer, oldest first — tickets come out in order."""
        with closing(
            self._conn.execute(
                "SELECT job_key, printer, fetch_path, description, payload, attempts, last_error"
                " FROM jobs WHERE printed_at IS NULL ORDER BY created_at, rowid LIMIT ?",
                (limit,),
            )
        ) as cur:
            rows = cur.fetchall()
        return [
            QueuedJob(
                job_key=row["job_key"],
                printer=row["printer"],
                fetch_path=row["fetch_path"],
                description=row["description"],
                payload=bytes(row["payload"]) if row["payload"] is not None else None,
                attempts=int(row["attempts"]),
                last_error=row["last_error"],
            )
            for row in rows
        ]

    def pending_count(self) -> int:
        with closing(
            self._conn.execute("SELECT COUNT(*) AS n FROM jobs WHERE printed_at IS NULL")
        ) as cur:
            return int(cur.fetchone()["n"])

    def mark_printed(self, job_key: str) -> None:
        """Only after the socket accepted the bytes. Before that the job must stay claimable."""
        self._conn.execute(
            "UPDATE jobs SET printed_at = ?, last_error = NULL WHERE job_key = ?",
            (_now(), job_key),
        )

    def abandon(self, job_key: str, error: str) -> None:
        """
        Stop owing a job the server will never serve — a 404, or a device no longer enrolled.

        It leaves the queue like a printed job, but the reason stays on the row: whoever asks why a
        ticket never came out needs to find it there. `mark_printed` clears `last_error` on purpose,
        so recording the reason and then marking printed would wipe it.
        """
        self._conn.execute(
            "UPDATE jobs SET printed_at = ?, attempts = attempts + 1, last_error = ?"
            " WHERE job_key = ?",
            (_now(), error[:500], job_key),
        )

    def record_failure(self, job_key: str, error: str) -> None:
        self._conn.execute(
            "UPDATE jobs SET attempts = attempts + 1, last_error = ? WHERE job_key = ?",
            (error[:500], job_key),
        )

    def is_printed(self, job_key: str) -> bool:
        with closing(
            self._conn.execute("SELECT printed_at FROM jobs WHERE job_key = ?", (job_key,))
        ) as cur:
            row = cur.fetchone()
        return bool(row and row["printed_at"])

    def purge_printed(self, keep_days: int = 14) -> int:
        """Old paper is not evidence; order_events is. Keep the queue small enough to stay fast."""
        cutoff = datetime.now(UTC).timestamp() - keep_days * 86400
        iso = datetime.fromtimestamp(cutoff, UTC).isoformat()
        with closing(
            self._conn.execute(
                "DELETE FROM jobs WHERE printed_at IS NOT NULL AND printed_at < ?", (iso,)
            )
        ) as cur:
            return cur.rowcount

    def all_jobs(self) -> Iterator[QueuedJob]:
        with closing(
            self._conn.execute(
                "SELECT job_key, printer, fetch_path, description, payload, attempts, last_error"
                " FROM jobs ORDER BY created_at, rowid"
            )
        ) as cur:
            for row in cur.fetchall():
                yield QueuedJob(
                    job_key=row["job_key"],
                    printer=row["printer"],
                    fetch_path=row["fetch_path"],
                    description=row["description"],
                    payload=bytes(row["payload"]) if row["payload"] is not None else None,
                    attempts=int(row["attempts"]),
                    last_error=row["last_error"],
                )
