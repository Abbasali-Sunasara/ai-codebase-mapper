import re
from pathlib import Path


# Earlier entries win ties when a file or symbol has multiple equally common roles.
CLASSIFICATION_PRIORITY = (
    "background_worker",
    "database_model",
    "api_route",
    "test",
    "api",
    "service",
    "model",
    "source",
)

WORKER_DECORATORS = {"task", "shared_task", "actor", "job"}
KNOWN_ORM_BASES = {
    "declarativebase",
    "declarativebasenometa",
    "mappedasdataclass",
    "model",
    "sqlmodel",
}
WORKER_FUNCTION_SUFFIX = re.compile(r"(?:^|_)(?:task|worker|job)s?$", re.IGNORECASE)
WORKER_CLASS_SUFFIX = re.compile(r"(?:Task|Worker|Job)s?$", re.IGNORECASE)


def _path_roles(path: str) -> list[str]:
    """Infer file roles from directory names and conventional Python filenames."""
    source_path = Path(path)
    parts = {part.lower() for part in source_path.parts[:-1]}
    stem = source_path.stem.lower()
    roles: list[str] = []

    is_test_file = stem.startswith("test_") or stem.endswith("_test") or stem in {"test", "tests"}
    if is_test_file or parts.intersection({"test", "tests"}):
        roles.append("test")

    is_worker_file = (
        stem in {"task", "tasks", "job", "jobs", "worker", "workers"}
        or bool(re.search(r"_(?:tasks?|jobs?|workers?)$", stem))
        or bool(parts.intersection({"task", "tasks", "job", "jobs", "worker", "workers"}))
    )
    if is_worker_file:
        roles.append("background_worker")

    is_api_file = (
        stem in {"api", "apis", "route", "routes"}
        or bool(re.search(r"_(?:api|apis|route|routes)$", stem))
        or bool(parts.intersection({"api", "apis", "route", "routes"}))
    )
    if is_api_file:
        roles.append("api")

    is_service_file = stem in {"service", "services"} or stem.endswith("_service") or "service" in parts or "services" in parts
    if is_service_file:
        roles.append("service")

    is_model_file = (
        stem in {"model", "models"}
        or bool(re.search(r"_models?$", stem))
        or bool(parts.intersection({"model", "models"}))
    )
    if is_model_file:
        roles.append("model")

    return roles


def _terminal_name(expression: str) -> str:
    """Return the final dotted identifier from an AST-unparsed expression."""
    target = expression.split("(", 1)[0].strip().lower()
    return target.rsplit(".", 1)[-1]


def _has_worker_decorator(symbol: dict) -> bool:
    for decorator in symbol.get("decorators", []):
        if _terminal_name(decorator) in WORKER_DECORATORS:
            return True
    return False


def _is_database_model(path: str, symbol: dict) -> bool:
    if symbol.get("kind") != "class":
        return False

    name = symbol.get("name", "")
    bases = [base.strip().lower() for base in symbol.get("bases", [])]
    base_terminals = {base.rsplit(".", 1)[-1] for base in bases}
    explicit_orm_base = any(
        terminal in KNOWN_ORM_BASES
        or base.endswith(".model")
        or base in {"django.db.models.model", "sqlalchemy.orm.declarative_base"}
        for base, terminal in ((base, base.rsplit(".", 1)[-1]) for base in bases)
    )
    has_orm_markers = bool(symbol.get("orm_markers"))
    has_model_name = name.lower().endswith("model") and name.lower() != "model"
    has_model_path = "model" in _path_roles(path)

    # A bare `Base` is too generic by itself. Require model naming/path context
    # or ORM-specific attributes before treating it as a database base class.
    has_contextual_base = "base" in base_terminals and (has_model_name or has_model_path or has_orm_markers)
    return explicit_orm_base or has_orm_markers or has_model_name or has_contextual_base


def _symbol_roles(path: str, symbol: dict | None, routes: list[dict] | None = None) -> list[str]:
    symbol = symbol or {}
    roles = list(_path_roles(path))
    if routes:
        roles.append("api_route")

    name = symbol.get("name", "")
    kind = symbol.get("kind")
    if _has_worker_decorator(symbol):
        roles.append("background_worker")
    elif kind == "function" and WORKER_FUNCTION_SUFFIX.search(name):
        roles.append("background_worker")
    elif kind == "class" and WORKER_CLASS_SUFFIX.search(name):
        roles.append("background_worker")

    if _is_database_model(path, symbol):
        roles.append("database_model")

    if not roles:
        roles.append("source")
    return [role for role in CLASSIFICATION_PRIORITY if role in set(roles)]


def _symbol_routes(symbol: dict, routes: list[dict]) -> list[dict]:
    identity = (symbol.get("name"), symbol.get("line"), symbol.get("scope"))
    return [
        route
        for route in routes
        if (route.get("name"), route.get("line"), route.get("scope")) == identity
    ]


def classify_file_roles(
    path: str,
    symbols: list[dict] | None = None,
    routes: list[dict] | None = None,
) -> list[str]:
    """Return every detected role for a file while preserving deterministic order."""
    symbols = symbols or []
    routes = routes or []
    roles: set[str] = set(_path_roles(path))
    for symbol in symbols:
        roles.update(_symbol_roles(path, symbol, _symbol_routes(symbol, routes)))
    if routes:
        roles.add("api_route")
    if not roles:
        roles.add("source")
    return [role for role in CLASSIFICATION_PRIORITY if role in roles]


def classify_file(path: str, symbols: list[dict] | None = None, routes: list[dict] | None = None) -> str:
    """Choose a stable primary file role without discarding its other role tags."""
    symbols = symbols or []
    routes = routes or []
    counts: dict[str, int] = {}

    for symbol in symbols:
        roles = _symbol_roles(path, symbol, _symbol_routes(symbol, routes))
        primary = roles[0]
        counts[primary] = counts.get(primary, 0) + 1

    if not counts:
        roles = classify_file_roles(path, symbols, routes)
        return roles[0]

    max_count = max(counts.values())
    return next(role for role in CLASSIFICATION_PRIORITY if counts.get(role) == max_count)
