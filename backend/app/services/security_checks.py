"""Backward-compatible entry point for repository security findings."""

from app.services.security_scanner import scan_security_findings


def scan_security(repo_path: str, file_metadata: dict | None = None) -> list[dict]:
    """Return the security findings produced by the unified heuristic scanner."""
    return scan_security_findings(repo_path, file_metadata)
