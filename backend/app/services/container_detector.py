from pathlib import Path
import re


CONTAINER_NAMES = {"dockerfile", ".dockerignore", "procfile"}
COMPOSE_PATTERN = re.compile(r"^(?:docker-compose|compose)(?:[._-].*)?\.ya?ml$", re.IGNORECASE)
DEPENDENCY_NAMES = {
    "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "pipfile", "pipfile.lock",
    "poetry.lock", "pdm.lock", "uv.lock", "package.json", "package-lock.json", "yarn.lock",
    "pnpm-lock.yaml", "go.mod", "cargo.toml", "gemfile", "gemfile.lock",
}
ENV_TEMPLATE_NAMES = {".env.example", ".env.sample", ".env.template", ".env.dist"}
SKIP_DIRECTORIES = {".git", "node_modules", "venv", ".venv", "env", "build", "dist", "__pycache__", "site-packages"}


def _role_for_path(path: Path) -> tuple[str, str] | None:
    name = path.name.lower()
    if name in CONTAINER_NAMES or name.startswith("dockerfile.") or COMPOSE_PATTERN.match(name):
        return "container", "infrastructure"
    if name in ENV_TEMPLATE_NAMES:
        return "environment_template", "config"
    if name in DEPENDENCY_NAMES or re.match(r"^requirements(?:[-_.].*)?\.txt$", name):
        return "dependency_manifest", "config"
    return None


def detect_containers(repo_path: str) -> list[dict[str, str]]:
    """Find container, dependency, and environment-template files.

    Results retain the historical ``file`` and ``kind`` keys while adding a
    role/classification usable by graph nodes and API clients.
    """
    root = Path(repo_path)
    results: list[dict[str, str]] = []
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part.lower() in SKIP_DIRECTORIES or part.startswith(".") for part in relative.parts[:-1]):
            continue
        role = _role_for_path(path)
        if role is None:
            continue
        kind, classification = role
        graph_role = "infrastructure" if classification == "infrastructure" else "config"
        results.append({
            "file": relative.as_posix(),
            "kind": kind,
            "role": graph_role,
            "classification": graph_role,
        })
    return sorted(results, key=lambda item: item["file"])
