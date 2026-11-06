from importlib.util import resolve_name
from pathlib import PurePosixPath
import posixpath

from app.services.classifier import classify_file, classify_file_roles


def _module_name(path: str) -> str:
    module = path[:-3].replace("/", ".") if path.endswith(".py") else path.replace("/", ".")
    return module.removesuffix(".__init__")


def _package_name(path: str) -> str:
    module = _module_name(path)
    return module if path.endswith("/__init__.py") else module.rpartition(".")[0]


def build_module_alias_index(paths: list[str]) -> dict[str, set[str]]:
    """Index package suffixes so imports resolve inside nested project roots."""
    index: dict[str, set[str]] = {}
    for path in paths:
        parts = _module_name(path).split(".")
        for start in range(len(parts)):
            for end in range(start + 1, len(parts) + 1):
                index.setdefault(".".join(parts[start:end]), set()).add(path)
    return index


def _all_language_alias_index(file_metadata: dict) -> dict[str, set[str]]:
    """Build path and basename aliases for relative, include, and Java imports."""
    index: dict[str, set[str]] = {}
    for path, metadata in file_metadata.items():
        if metadata.get("error"):
            continue
        pure = PurePosixPath(path)
        stem_path = str(pure.with_suffix(""))
        aliases = {path, stem_path, stem_path.replace("/", "."), pure.stem}
        parts = stem_path.split("/")
        for start in range(len(parts)):
            suffix = "/".join(parts[start:])
            aliases.add(suffix)
            aliases.add(suffix.replace("/", "."))
        if pure.name == "index.js" or pure.name == "index.ts":
            aliases.add(str(pure.parent))
            aliases.add(str(pure.parent).replace("/", "."))
        for alias in aliases:
            if alias:
                index.setdefault(alias, set()).add(path)
    return index


def _resolve_non_python_import(path: str, imported: str, aliases: dict[str, set[str]]) -> str | None:
    target = imported.strip().strip("\"'")
    if not target:
        return None
    if target.startswith("."):
        relative = posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
        for candidate in (relative, f"{relative}.js", f"{relative}.jsx", f"{relative}.ts", f"{relative}.tsx",
                          f"{relative}.c", f"{relative}.h", f"{relative}.cpp", f"{relative}.hpp", f"{relative}.cc", f"{relative}.java",
                          f"{relative}/index.js", f"{relative}/index.ts"):
            matches = aliases.get(candidate, set())
            if len(matches) == 1:
                return next(iter(matches))
        return None
    matches = aliases.get(target, set())
    if len(matches) == 1:
        resolved = next(iter(matches))
        return None if resolved == path else resolved
    # Java packages use dotted qualified names; quoted C/C++ includes typically
    # resolve by header basename in the repository.
    dotted = target.replace(".", "/")
    for candidate in (dotted, f"{dotted}.java", target.rsplit("/", 1)[-1]):
        matches = aliases.get(candidate, set())
        if len(matches) == 1:
            resolved = next(iter(matches))
            return None if resolved == path else resolved
    return None


def build_dependency_graph(file_metadata: dict) -> tuple[list[dict], list[dict]]:
    """Build evidence-bearing file nodes and internal import edges."""
    module_index = build_module_alias_index([
        path
        for path, metadata in file_metadata.items()
        if metadata.get("file_type", "python" if path.endswith(".py") else "source") == "python"
        and "error" not in metadata
    ])
    all_language_aliases = _all_language_alias_index(file_metadata)
    nodes = []
    edges = []
    for path, metadata in file_metadata.items():
        nodes.append({
            "id": path,
            "type": "module",
            "file_type": metadata.get("file_type", "python" if path.endswith(".py") else "source"),
            "classification": metadata.get("classification", "source"),
            "classifications": metadata.get("classifications", [metadata.get("classification", "source")]),
            "file": path,
            "name": path,
            "evidence": {"file": path, "line": 1},
            "symbols": metadata.get("symbols", []),
            "file_symbols": metadata.get("file_symbols", metadata.get("symbols", [])),
            "evidence_symbols": metadata.get("evidence_symbols", []),
            "line_count": metadata.get("line_count", 0),
            "file_path": metadata.get("file_path", path),
            "exports_or_includes": metadata.get("exports_or_includes", []),
            "line_numbers": metadata.get("line_numbers", {}),
            "security_warnings": metadata.get("security_warnings", []),
            "heuristics": metadata.get("heuristics", []),
        })
        routes_by_symbol: dict[tuple, list[dict]] = {}
        for route in metadata.get("routes", []):
            identity = (route.get("name"), route.get("line"), route.get("scope"))
            routes_by_symbol.setdefault(identity, []).append(route)
        for symbol in metadata.get("symbols", []):
            identity = (symbol.get("name"), symbol.get("line"), symbol.get("scope"))
            symbol_routes = routes_by_symbol.get(identity, [])
            symbol_classifications = classify_file_roles(path, [symbol], symbol_routes)
            symbol_classification = classify_file(path, [symbol], symbol_routes)
            symbol_id = f"{path}::{symbol['kind']}::{symbol['line']}::{symbol['name']}"
            nodes.append({
                "id": symbol_id,
                "type": symbol_classification,
                "classification": symbol_classification,
                "classifications": symbol_classifications,
                "file": path,
                "name": symbol["name"],
                "evidence": {"file": path, "line": symbol["line"]},
                "details": symbol,
            })
            edges.append({
                "source": path,
                "target": symbol_id,
                "type": "contains",
                "line": symbol["line"],
                "evidence": {"file": path, "line": symbol["line"]},
            })
        if metadata.get("error"):
            continue
        seen_edges = set()
        for imported in metadata.get("import_evidence", []):
            name = imported["module"]
            is_python = metadata.get("file_type", "python" if path.endswith(".py") else "source") == "python"
            if is_python and name.startswith("."):
                package = _package_name(path)
                try:
                    name = resolve_name(name, package)
                except (ImportError, ValueError):
                    continue
            if is_python:
                candidates = module_index.get(name, set())
                target = next(iter(candidates)) if len(candidates) == 1 else None
            else:
                target = _resolve_non_python_import(path, name, all_language_aliases)
            if target is None:
                continue
            key = (path, target, imported["line"])
            if key in seen_edges:
                continue
            seen_edges.add(key)
            edges.append({
                "source": path,
                "target": target,
                "type": "imports",
                "line": imported["line"],
                "evidence": {"file": path, "line": imported["line"], "import": imported["module"]},
            })
    return nodes, edges
