import ast
import os
from typing import Any

from app.services.classifier import classify_file, classify_file_roles
from app.services.graph_builder import build_dependency_graph, build_module_alias_index
from app.services.graph_metrics import calculate_graph_metrics
from app.services.security_scanner import scan_repository_security


SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "env", "build", "dist", "__pycache__", "site-packages"}
HTTP_ROUTE_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}
ROUTE_DECORATORS = HTTP_ROUTE_METHODS | {"route", "api_route", "websocket", "websocket_route"}


def _expression_name(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except (AttributeError, ValueError):
        return type(node).__name__


def _literal(node: ast.AST | None) -> Any:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return None


def _decorator_parts(node: ast.AST) -> tuple[str, list[ast.AST], dict[str, ast.AST]]:
    """Return the decorator's terminal name, positional arguments, and keywords."""
    call = node if isinstance(node, ast.Call) else None
    target = call.func if call else node
    terminal = _expression_name(target).rsplit(".", 1)[-1].lower()
    positional = call.args if call else []
    keywords = {keyword.arg: keyword.value for keyword in call.keywords if keyword.arg} if call else {}
    return terminal, positional, keywords


def _route_path(positional: list[ast.AST], keywords: dict[str, ast.AST]) -> str | None:
    candidate = positional[0] if positional else keywords.get("path") or keywords.get("rule")
    value = _literal(candidate)
    return value if isinstance(value, str) else None


def _route_methods(terminal: str, keywords: dict[str, ast.AST]) -> list[str]:
    declared = _literal(keywords.get("methods"))
    if isinstance(declared, str):
        declared = [declared]
    if isinstance(declared, (list, tuple, set, frozenset)):
        methods = list(dict.fromkeys(str(method).upper() for method in declared if str(method).strip()))
        if methods:
            return methods

    if terminal in HTTP_ROUTE_METHODS:
        return [terminal.upper()]
    if terminal in {"websocket", "websocket_route"}:
        return ["WEBSOCKET"]
    if terminal == "api_route":
        return ["ANY"]
    # Flask-style `route` defaults to GET when no methods are declared.
    return ["GET"]


def _has_auth_dependency(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    dependency_names = [
        _expression_name(call).lower()
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and _expression_name(call.func).rsplit(".", 1)[-1] in {"Depends", "Security"}
    ]
    return any(
        any(word in dependency for word in ("auth", "user", "permission", "principal"))
        for dependency in dependency_names
    )


def _class_orm_markers(node: ast.ClassDef) -> list[str]:
    markers: list[str] = []
    orm_names = {"column", "mapped_column", "mapped", "relationship", "foreignkey"}
    for statement in node.body:
        targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target] if isinstance(statement, ast.AnnAssign) else []
        value = statement.value if isinstance(statement, (ast.Assign, ast.AnnAssign)) else None
        annotation = statement.annotation if isinstance(statement, ast.AnnAssign) else None
        expressions = [expression for expression in (value, annotation) if expression is not None]
        is_table_name = any(isinstance(target, ast.Name) and target.id == "__tablename__" for target in targets)
        has_orm_construct = any(
            isinstance(child, (ast.Name, ast.Attribute))
            and _expression_name(child).rsplit(".", 1)[-1].lower() in orm_names
            for expression in expressions
            for child in ast.walk(expression)
        )
        if is_table_name or has_orm_construct:
            marker = next((target.id for target in targets if isinstance(target, ast.Name)), "__tablename__")
            markers.append(marker)
    return list(dict.fromkeys(markers))


class CodebaseASTParser(ast.NodeVisitor):
    """Extract source facts and line evidence without executing repository code."""

    def __init__(self):
        self.classes: list[str] = []
        self.functions: list[str] = []
        self.imports: list[str] = []
        self.import_evidence: list[dict[str, Any]] = []
        self.symbols: list[dict[str, Any]] = []
        self.routes: list[dict[str, Any]] = []
        self.scope_stack: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef):
        bases = [_expression_name(base) for base in node.bases]
        decorators = [_expression_name(decorator) for decorator in node.decorator_list]
        fields = []
        for statement in node.body:
            targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target] if isinstance(statement, ast.AnnAssign) else []
            fields.extend(target.id for target in targets if isinstance(target, ast.Name) and not target.id.startswith("__"))
        self.classes.append(node.name)
        self.symbols.append({
            "kind": "class",
            "name": node.name,
            "line": node.lineno,
            "end_line": node.end_lineno,
            "scope": ".".join(self.scope_stack) or None,
            "bases": bases,
            "decorators": decorators,
            "fields": fields,
            "orm_markers": _class_orm_markers(node),
        })
        self.scope_stack.append(node.name)
        try:
            self.generic_visit(node)
        finally:
            self.scope_stack.pop()

    def _visit_function(self, node):
        decorator_nodes = node.decorator_list
        decorators = [_expression_name(item) for item in decorator_nodes]
        args = [arg.arg for arg in (*node.args.posonlyargs, *node.args.args)]
        if node.args.vararg:
            args.append(node.args.vararg.arg)
        args.extend(arg.arg for arg in node.args.kwonlyargs)
        if node.args.kwarg:
            args.append(node.args.kwarg.arg)
        scope = ".".join(self.scope_stack) or None
        self.functions.append(node.name)
        self.symbols.append({
            "kind": "function",
            "name": node.name,
            "line": node.lineno,
            "end_line": node.end_lineno,
            "scope": scope,
            "arguments": args,
            "decorators": decorators,
        })
        for decorator_node, decorator in zip(decorator_nodes, decorators):
            terminal, positional, keywords = _decorator_parts(decorator_node)
            if terminal not in ROUTE_DECORATORS:
                continue
            for method in _route_methods(terminal, keywords):
                self.routes.append({
                    "name": node.name,
                    "method": method,
                    "path": _route_path(positional, keywords),
                    "line": node.lineno,
                    "scope": scope,
                    "decorator": decorator,
                    "has_auth_dependency": _has_auth_dependency(node),
                })
        self.scope_stack.append(node.name)
        try:
            self.generic_visit(node)
        finally:
            self.scope_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._visit_function(node)

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.append(alias.name)
            self.import_evidence.append({"module": alias.name, "line": node.lineno, "kind": "import"})

    def visit_ImportFrom(self, node: ast.ImportFrom):
        base = "." * node.level + (node.module or "")
        if base:
            self.imports.append(base)
            self.import_evidence.append({"module": base, "line": node.lineno, "kind": "from"})
        for alias in node.names:
            if node.module and alias.name != "*":
                self.import_evidence.append({"module": f"{node.module}.{alias.name}", "line": node.lineno, "kind": "from_member"})


def analyze_repository_ast(repo_path: str) -> dict[str, Any]:
    """Parse Python files and return metadata plus file-to-file import edges."""
    file_metadata: dict[str, dict[str, Any]] = {}
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS and not name.startswith(".")]
        for filename in files:
            if not filename.endswith(".py"):
                continue
            full_path = os.path.join(root, filename)
            if os.path.islink(full_path):
                continue
            relative = os.path.relpath(full_path, repo_path).replace(os.sep, "/")
            try:
                with open(full_path, encoding="utf-8") as source_file:
                    source = source_file.read()
                tree = ast.parse(source, filename=relative)
                parser = CodebaseASTParser()
                parser.visit(tree)
                routes_by_symbol: dict[tuple, list[dict[str, Any]]] = {}
                for route in parser.routes:
                    identity = (route["name"], route["line"], route["scope"])
                    routes_by_symbol.setdefault(identity, []).append(route)
                for symbol in parser.symbols:
                    identity = (symbol["name"], symbol["line"], symbol["scope"])
                    symbol_routes = routes_by_symbol.get(identity, [])
                    symbol["classification"] = classify_file(relative, [symbol], symbol_routes)
                    symbol["classifications"] = classify_file_roles(relative, [symbol], symbol_routes)
                file_metadata[relative] = {
                    "file_type": "python",
                    "classes": parser.classes,
                    "functions": parser.functions,
                    "imports": list(dict.fromkeys(parser.imports)),
                    "import_evidence": parser.import_evidence,
                    "symbols": parser.symbols,
                    "routes": parser.routes,
                    "line_count": len(source.splitlines()),
                    "classification": classify_file(relative, parser.symbols, parser.routes),
                    "classifications": classify_file_roles(relative, parser.symbols, parser.routes),
                }
            except (OSError, UnicodeError, SyntaxError, ValueError) as error:
                file_metadata[relative] = {
                    "file_type": "python",
                    "error": str(error),
                    "line": getattr(error, "lineno", None),
                }

    security_analysis = scan_repository_security(repo_path, file_metadata)
    python_file_paths = [
        path for path, metadata in file_metadata.items()
        if metadata.get("file_type") == "python" and not metadata.get("error")
    ]
    module_index = build_module_alias_index(python_file_paths)
    for path, metadata in file_metadata.items():
        if metadata.get("error"):
            continue
        internal, external = [], []
        for imported in metadata["imports"]:
            normalized = imported.lstrip(".")
            destination = internal if normalized in module_index else external
            destination.append(imported)
        metadata["internal_imports"] = list(dict.fromkeys(internal))
        metadata["external_imports"] = list(dict.fromkeys(external))

    nodes, edges = build_dependency_graph(file_metadata)
    module_nodes = [node for node in nodes if node["type"] == "module"]
    module_edges = [edge for edge in edges if edge["type"] == "imports"]
    python_module_nodes = [node for node in module_nodes if node.get("file_type") == "python"]
    metrics = calculate_graph_metrics(python_module_nodes, module_edges)
    return {
        "nodes_count": len(module_nodes),
        "edges_count": len(module_edges),
        "python_files_count": len(python_file_paths),
        "component_nodes_count": len(nodes) - len(module_nodes),
        "file_metadata": file_metadata,
        "nodes": nodes,
        "edges": edges,
        "module_nodes": module_nodes,
        "module_edges": module_edges,
        "graph_summary": module_nodes[:20],
        "graph_metrics": metrics,
        **security_analysis,
    }
