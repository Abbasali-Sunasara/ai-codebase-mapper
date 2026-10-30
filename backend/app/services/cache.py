import json
import sqlite3
from pathlib import Path

from app.core.config import settings


class SQLiteCache:
    """Small persistent cache for commit analyses and content-addressed summaries."""

    def __init__(self, db_path: str | None = None):
        self.path = Path(db_path or settings.cache_db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS analyses (commit_sha TEXT PRIMARY KEY, result TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS summaries (file_hash TEXT PRIMARY KEY, summary TEXT NOT NULL)")

    def _connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def get_analysis(self, commit_sha: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute("SELECT result FROM analyses WHERE commit_sha = ?", (commit_sha,)).fetchone()
        return json.loads(row[0]) if row else None

    def put_analysis(self, commit_sha: str, result: dict) -> None:
        with self._connect() as connection:
            connection.execute("INSERT OR REPLACE INTO analyses(commit_sha, result) VALUES (?, ?)", (commit_sha, json.dumps(result)))

    def get_summary(self, file_hash: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute("SELECT summary FROM summaries WHERE file_hash = ?", (file_hash,)).fetchone()
        return row[0] if row else None

    def put_summary(self, file_hash: str, summary: str) -> None:
        with self._connect() as connection:
            connection.execute("INSERT OR REPLACE INTO summaries(file_hash, summary) VALUES (?, ?)", (file_hash, summary))


cache = SQLiteCache()
