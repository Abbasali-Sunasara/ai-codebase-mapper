import hashlib
import re
from pathlib import Path

from app.core.ai_client import ai_client
from app.services.cache import cache


def summarize_metadata(file_metadata: dict, repo_path: str, limit: int = 3) -> dict[str, str]:
    """Enrich deterministic AST metadata with optional natural-language summaries."""
    summaries = {}
    for path, metadata in file_metadata.items():
        if len(summaries) >= limit:
            break
        if not isinstance(metadata, dict) or metadata.get("error") or not (metadata.get("classes") or metadata.get("functions")):
            continue
        try:
            source = (Path(repo_path) / path).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        file_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        summary = cache.get_summary(file_hash)
        if summary is None:
            numbered_source = "\n".join(f"L{line_number} {line}" for line_number, line in enumerate(source.splitlines(), 1))
            summary = ai_client.explain_code_component(
                file_path=path,
                code_snippet=numbered_source,
                metadata=metadata,
            )
            cited_lines = [int(match) for match in re.findall(r"\bL(\d+)\b", summary)]
            invalid_lines = [line for line in cited_lines if line < 1 or line > len(source.splitlines())]
            if invalid_lines:
                summary = f"Summary withheld: citation to nonexistent line {invalid_lines[0]} failed evidence validation."
            elif not summary.startswith("AI summarization unavailable:"):
                cache.put_summary(file_hash, summary)
        summaries[path] = summary
    return summaries
