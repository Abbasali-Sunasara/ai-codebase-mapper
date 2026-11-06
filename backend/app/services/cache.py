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
            connection.execute(
                """CREATE TABLE IF NOT EXISTS file_scans (
                    namespace TEXT NOT NULL,
                    path TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL DEFAULT '',
                    mtime_ns INTEGER NOT NULL,
                    size INTEGER NOT NULL,
                    ast_metadata TEXT,
                    security_findings TEXT,
                    PRIMARY KEY (namespace, path, content_hash)
                )"""
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(file_scans)")}
            if "snapshot_id" not in columns:
                connection.execute("ALTER TABLE file_scans ADD COLUMN snapshot_id TEXT NOT NULL DEFAULT ''")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS file_scans_by_snapshot_stat ON file_scans(namespace, path, snapshot_id, mtime_ns, size)"
            )

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def get_file_scan(
        self,
        namespace: str,
        path: str,
        *,
        mtime_ns: int | None = None,
        size: int | None = None,
        content_hash: str | None = None,
        snapshot_id: str | None = None,
    ) -> dict | None:
        """Read cached AST/security results by unchanged stat or content digest."""
        if content_hash is not None:
            query = """SELECT ast_metadata, security_findings FROM file_scans
                       WHERE namespace = ? AND path = ? AND content_hash = ?"""
            params = (namespace, path, content_hash)
        elif mtime_ns is not None and size is not None:
            query = """SELECT ast_metadata, security_findings FROM file_scans
                       WHERE namespace = ? AND path = ? AND snapshot_id = ? AND mtime_ns = ? AND size = ?
                       ORDER BY rowid DESC LIMIT 1"""
            params = (namespace, path, snapshot_id or "", mtime_ns, size)
        else:
            return None
        with self._connect() as connection:
            row = connection.execute(query, params).fetchone()
        if row is None:
            return None
        return {
            "ast_metadata": json.loads(row[0]) if row[0] is not None else None,
            "security_findings": json.loads(row[1]) if row[1] is not None else None,
        }

    def put_file_scan(
        self,
        namespace: str,
        path: str,
        content_hash: str,
        mtime_ns: int,
        size: int,
        *,
        snapshot_id: str | None = None,
        ast_metadata: dict | None = None,
        security_findings: list | None = None,
    ) -> None:
        """Persist available per-file results without overwriting other cached stages."""
        ast_json = json.dumps(ast_metadata) if ast_metadata is not None else None
        findings_json = json.dumps(security_findings) if security_findings is not None else None
        with self._connect() as connection:
            # Retain only the latest content version per repository-relative path.
            connection.execute(
                "DELETE FROM file_scans WHERE namespace = ? AND path = ? AND content_hash <> ?",
                (namespace, path, content_hash),
            )
            connection.execute(
                """INSERT INTO file_scans
                   (namespace, path, content_hash, snapshot_id, mtime_ns, size, ast_metadata, security_findings)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(namespace, path, content_hash) DO UPDATE SET
                     snapshot_id = excluded.snapshot_id,
                     mtime_ns = excluded.mtime_ns,
                     size = excluded.size,
                     ast_metadata = COALESCE(excluded.ast_metadata, file_scans.ast_metadata),
                     security_findings = COALESCE(excluded.security_findings, file_scans.security_findings)""",
                (namespace, path, content_hash, snapshot_id or "", mtime_ns, size, ast_json, findings_json),
            )

    def prune_file_scans(self, namespace: str, active_paths: list[str]) -> None:
        """Drop cached entries for files removed from the current repository snapshot."""
        with self._connect() as connection:
            connection.execute("CREATE TEMP TABLE IF NOT EXISTS active_scan_paths(path TEXT PRIMARY KEY)")
            connection.execute("DELETE FROM active_scan_paths")
            connection.executemany(
                "INSERT OR IGNORE INTO active_scan_paths(path) VALUES (?)",
                ((path,) for path in active_paths),
            )
            connection.execute(
                """DELETE FROM file_scans
                   WHERE namespace = ? AND NOT EXISTS (
                     SELECT 1 FROM active_scan_paths AS active WHERE active.path = file_scans.path
                   )""",
                (namespace,),
            )

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
