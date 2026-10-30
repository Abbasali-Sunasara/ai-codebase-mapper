from importlib.util import resolve_name

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


def build_dependency_graph(file_metadata: dict) -> tuple[list[dict], list[dict]]:
    """Build evidence-bearing file nodes and internal import edges."""
    module_index = build_module_alias_index([
        path
        for path, metadata in file_metadata.items()
        if metadata.get("file_type", "python" if path.endswith(".py") else "source") == "python"
        and "error" not in metadata
    ])
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
            "security_warnings": metadata.get("security_warnings", []),
            "heuristics": metadata.get("heuristics", []),
        })
        if metadata.get("file_type", "python" if path.endswith(".py") else "source") != "python":
            continue
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
            if name.startswith("."):
                package = _package_name(path)
                try:
                    name = resolve_name(name, package)
                except (ImportError, ValueError):
                    continue
            candidates = module_index.get(name, set())
            target = next(iter(candidates)) if len(candidates) == 1 else None
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
