"""Deterministic security and infrastructure heuristics for repository snapshots."""

import ast
from collections import defaultdict
from pathlib import Path
import re
from typing import Any

import yaml
from yaml.nodes import MappingNode, ScalarNode, SequenceNode

from app.services.container_detector import detect_containers


SKIP_DIRECTORIES = {".git", "node_modules", "venv", ".venv", "env", "build", "dist", "__pycache__", "site-packages"}
SCANNABLE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".json", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".conf", ".env", ".sh", ".tf", ".properties", ".xml",
}
SECRET_NAME = r"(?:api[_-]?key|access[_-]?key|secret(?:[_-]?key)?|password|passwd|token|client[_-]?secret|private[_-]?key)"
SECRET_QUOTED_PATTERN = re.compile(
    rf"(?i)(?<![a-z0-9]){SECRET_NAME}\b\s*[:=]\s*(['\"])(?P<value>[^'\"\r\n]{{8,}})\1"
)
SECRET_UNQUOTED_PATTERN = re.compile(
    rf"(?i)(?<![a-z0-9]){SECRET_NAME}\b\s*[:=]\s*(?!['\"$])(?P<value>[^\s,;#]{{12,}})"
)
CONNECTION_URL_CREDENTIAL_PATTERN = re.compile(
    r"(?i)\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis)://[^:/@\s]+:(?P<value>[^@\s/]+)@"
)
DEBUG_TEXT_PATTERN = re.compile(r"(?i)\bdebug\s*[:=]\s*true\b")
RELOAD_TEXT_PATTERN = re.compile(r"(?i)\breload\s*[:=]\s*true\b")
PRODUCTION_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:environment|env|stage|deployment)\b\s*[:=]\s*['\"]?(?:prod|production)\b"
)
PRODUCTION_PATH_PARTS = {"prod", "production", "deploy", "deployment", "release"}
AUTH_MARKER_PATTERN = re.compile(r"(?i)(?:auth|login_required|permission_required|jwt_required|requires?_auth|authenticated)")
SENSITIVE_ROUTE_PATTERN = re.compile(r"(?i)(?:admin|account|users?|profile|payment|billing|settings|private|credential)")
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
PLACEHOLDER_SECRET_PARTS = (
    "placeholder", "replace", "your_", "your-", "example", "sample", "dummy", "fake",
    "changeme", "change_me", "xxx", "<your", "<replace", "...",
)
UNQUOTED_SECRET_EXTENSIONS = {".env", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".properties"}
SENSITIVE_HOST_PORTS = {22, 2375, 3306, 5432, 6379, 9200, 1433, 1521, 27017}


def _skip_path(relative: Path) -> bool:
    return any(part.lower() in SKIP_DIRECTORIES or part == ".git" for part in relative.parts[:-1])


def _is_scannable(path: Path) -> bool:
    name = path.name.lower()
    return (
        path.suffix.lower() in SCANNABLE_EXTENSIONS
        or name in {".env", ".env.example", ".env.sample", ".env.template", ".env.dist", "dockerfile", ".dockerignore"}
        or name.startswith("dockerfile.")
        or name.startswith("docker-compose.")
        or name.startswith("compose.")
        or name.startswith("requirements") and name.endswith(".txt")
    )


def _is_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return (
        not normalized
        or any(part in normalized for part in PLACEHOLDER_SECRET_PARTS)
        or normalized.startswith(("${", "$env:", "os.environ", "getenv("))
    )


def _line_finding(path: str, line: int, finding_type: str, severity: str, message: str) -> dict[str, Any]:
    return {
        "file": path,
        "line": line,
        "type": finding_type,
        "severity": severity,
        "message": message,
        "description": message,
    }


def _is_dockerfile(path: str) -> bool:
    name = Path(path).name.lower()
    return name == "dockerfile" or name.startswith("dockerfile.")


def _dockerfile_findings(path: str, source: str, line_offset: int = 0) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(source.splitlines(), start=1):
        instruction = raw_line.split("#", 1)[0].strip()
        if not instruction:
            continue
        user_match = re.match(r"(?i)^USER\s+(\S+)", instruction)
        if user_match:
            user = user_match.group(1).split(":", 1)[0].lower()
            if user in {"root", "0"}:
                findings.append(_line_finding(
                    path,
                    line_number + line_offset,
                    "container_runs_as_root",
                    "high",
                    "The image explicitly runs as root; use a dedicated non-root user where possible.",
                ))

        from_match = re.match(r"(?i)^FROM\s+(.+)$", instruction)
        if not from_match:
            continue
        parts = from_match.group(1).split()
        image = next((part for part in parts if not part.startswith("--")), "")
        if not image or image.lower() == "scratch" or image.startswith("$") or "@sha256:" in image.lower():
            continue
        final_component = image.rsplit("/", 1)[-1]
        tag = final_component.rsplit(":", 1)[1] if ":" in final_component else None
        if tag is None or tag.lower() == "latest":
            findings.append(_line_finding(
                path,
                line_number + line_offset,
                "unpinned_container_base_image",
                "medium",
                f"Base image '{image}' has no fixed version tag or uses the mutable 'latest' tag.",
            ))
    return findings


def _yaml_scalar(node: Any) -> str | None:
    return node.value if isinstance(node, ScalarNode) else None


def _host_port_from_mapping(value: Any) -> int | None:
    if isinstance(value, MappingNode):
        for key_node, value_node in value.value:
            key = (_yaml_scalar(key_node) or "").lower()
            if key in {"published", "hostport"}:
                raw_port = _yaml_scalar(value_node)
                if raw_port and raw_port.isdigit():
                    return int(raw_port)
    return None


def _host_port_from_string(value: str) -> int | None:
    # Compose short syntax is HOST:CONTAINER or IP:HOST:CONTAINER. A single
    # container-only port does not publish a host port and is intentionally skipped.
    port_spec = value.split("/", 1)[0].strip().strip("\"'")
    parts = port_spec.split(":")
    if len(parts) < 2:
        return None
    host_port = parts[-2]
    if host_port.isdigit():
        return int(host_port)
    range_start = host_port.split("-", 1)[0]
    return int(range_start) if range_start.isdigit() else None


def _yaml_findings(path: str, source: str) -> list[dict[str, Any]]:
    """Parse YAML safely and inspect its syntax tree to retain exact source lines."""
    try:
        # Use safe_load as the data validation/router step; compose provides source marks.
        yaml.safe_load(source)
        root = yaml.compose(source, Loader=yaml.SafeLoader)
    except yaml.YAMLError:
        return []
    if root is None:
        return []

    findings: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()

    def add(node: Any, finding_type: str, severity: str, message: str, line: int | None = None) -> None:
        line = line if line is not None else node.start_mark.line + 1
        key = (line, finding_type)
        if key not in seen:
            seen.add(key)
            findings.append(_line_finding(path, line, finding_type, severity, message))

    def inspect_ports(node: Any) -> None:
        candidates = node.value if isinstance(node, SequenceNode) else [node]
        for candidate in candidates:
            if isinstance(candidate, MappingNode):
                port = _host_port_from_mapping(candidate)
                port_node = next((
                    value_node for key_node, value_node in candidate.value
                    if (_yaml_scalar(key_node) or "").lower() in {"published", "hostport"}
                ), candidate)
                if port in SENSITIVE_HOST_PORTS:
                    add(port_node, "sensitive_host_port_exposed", "high", f"Sensitive host port {port} is explicitly published.")
            elif isinstance(candidate, ScalarNode):
                port = _host_port_from_string(candidate.value)
                if port in SENSITIVE_HOST_PORTS:
                    add(candidate, "sensitive_host_port_exposed", "high", f"Sensitive host port {port} is explicitly published.")

    def walk(node: Any) -> None:
        if isinstance(node, MappingNode):
            for key_node, value_node in node.value:
                key = (_yaml_scalar(key_node) or "").lower()
                value = (_yaml_scalar(value_node) or "").strip().lower()
                if key == "debug" and value in {"true", "1", "yes", "on"}:
                    add(value_node, "debug_mode_enabled", "medium", "Debug mode is enabled in this YAML configuration.")
                elif key == "privileged" and value in {"true", "yes", "on"}:
                    add(value_node, "container_privileged_mode", "high", "Container privileged mode is enabled.")
                elif key == "hostport" and value.isdigit() and int(value) in SENSITIVE_HOST_PORTS:
                    add(value_node, "sensitive_host_port_exposed", "high", f"Sensitive host port {value} is explicitly published.")
                elif key == "ports":
                    inspect_ports(value_node)

                # Compose accepts environment as a mapping, a list of KEY=value
                # strings, or a multiline scalar block. Preserve each value's line.
                if key == "environment":
                    if isinstance(value_node, SequenceNode):
                        env_entries = ((env_node, _yaml_scalar(env_node), None) for env_node in value_node.value)
                    elif isinstance(value_node, ScalarNode):
                        env_entries = (
                            (value_node, env_line, value_node.start_mark.line + offset + 1)
                            for offset, env_line in enumerate(value_node.value.splitlines())
                        )
                    else:
                        env_entries = ()
                    for env_node, env_value, source_line in env_entries:
                        match = re.match(r"(?i)^\s*DEBUG\s*=\s*(true|1|yes|on)\s*$", env_value or "")
                        if match:
                            add(
                                env_node,
                                "debug_mode_enabled",
                                "medium",
                                "Debug mode is enabled in a YAML environment variable.",
                                line=source_line,
                            )

                if key == "dockerfile_inline" and isinstance(value_node, ScalarNode):
                    findings.extend(_dockerfile_findings(
                        path,
                        value_node.value,
                        line_offset=value_node.start_mark.line,
                    ))
                walk(value_node)
        elif isinstance(node, SequenceNode):
            for child in node.value:
                walk(child)

    walk(root)
    return findings


def _source_findings(path: str, source: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    production_context = bool(PRODUCTION_CONTEXT_PATTERN.search(source)) or any(
        re.search(r"(?:^|[._-])(?:prod|production|deploy|deployment|release)(?:[._-]|$)", part.lower())
        for part in Path(path).parts
    )

    for line_number, line in enumerate(source.splitlines(), start=1):
        secret_match = SECRET_QUOTED_PATTERN.search(line)
        if secret_match is None and (
            Path(path).suffix.lower() in UNQUOTED_SECRET_EXTENSIONS
            or Path(path).name.lower().startswith(".env")
            or Path(path).name.lower().startswith("dockerfile")
        ):
            secret_match = SECRET_UNQUOTED_PATTERN.search(line)
        if secret_match and not _is_placeholder(secret_match.group("value")):
            findings.append(_line_finding(
                path,
                line_number,
                "possible_hardcoded_secret",
                "high",
                "Possible hardcoded credential; review this line without exposing the value.",
            ))
        elif connection_match := CONNECTION_URL_CREDENTIAL_PATTERN.search(line):
            if not _is_placeholder(connection_match.group("value")):
                findings.append(_line_finding(
                    path,
                    line_number,
                    "possible_hardcoded_secret",
                    "high",
                    "A database connection URL appears to contain embedded credentials.",
                ))
        if DEBUG_TEXT_PATTERN.search(line):
            findings.append(_line_finding(
                path, line_number, "debug_mode_enabled", "medium", "Debug mode is explicitly enabled."
            ))
        if production_context and RELOAD_TEXT_PATTERN.search(line):
            findings.append(_line_finding(
                path,
                line_number,
                "development_reload_enabled_in_production",
                "medium",
                "Automatic development reload appears enabled in a production-like context.",
            ))

    if path.lower().endswith(".py"):
        findings.extend(_ast_debug_findings(path, source, production_context))
    if _is_dockerfile(path):
        findings.extend(_dockerfile_findings(path, source))
    elif Path(path).suffix.lower() in {".yml", ".yaml"}:
        findings.extend(_yaml_findings(path, source))
    return findings


def _target_names(target: ast.AST) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id.lower()}
    if isinstance(target, ast.Attribute):
        return {target.attr.lower()}
    if isinstance(target, (ast.Tuple, ast.List)):
        return set().union(*(_target_names(item) for item in target.elts)) if target.elts else set()
    return set()


def _is_true_literal(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _ast_debug_findings(path: str, source: str, production_context: bool) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(source, filename=path)
    except (SyntaxError, ValueError):
        return []

    findings: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        assignments: list[tuple[set[str], ast.AST]] = []
        if isinstance(node, ast.Assign):
            assignments.extend((_target_names(target), node.value) for target in node.targets)
        elif isinstance(node, ast.AnnAssign):
            assignments.append((_target_names(node.target), node.value) if node.value is not None else (set(), ast.Constant(False)))
        elif isinstance(node, ast.NamedExpr):
            assignments.append((_target_names(node.target), node.value))

        for names, value in assignments:
            if "debug" in names and _is_true_literal(value):
                findings.append(_line_finding(
                    path, node.lineno, "debug_mode_enabled", "medium", "Debug mode is explicitly enabled."
                ))
            if production_context and "reload" in names and _is_true_literal(value):
                findings.append(_line_finding(
                    path,
                    node.lineno,
                    "development_reload_enabled_in_production",
                    "medium",
                    "Automatic development reload appears enabled in a production-like context.",
                ))

        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg == "debug" and _is_true_literal(keyword.value):
                    findings.append(_line_finding(
                        path, node.lineno, "debug_mode_enabled", "medium", "Debug mode is explicitly enabled."
                    ))
                elif production_context and keyword.arg == "reload" and _is_true_literal(keyword.value):
                    findings.append(_line_finding(
                        path,
                        node.lineno,
                        "development_reload_enabled_in_production",
                        "medium",
                        "Automatic development reload appears enabled in a production-like context.",
                    ))
    return findings


def _route_auth_expected(route: dict[str, Any]) -> bool:
    method = str(route.get("method", "")).upper()
    route_name = str(route.get("name", ""))
    route_path = str(route.get("path") or "")
    return method in MUTATING_METHODS or bool(SENSITIVE_ROUTE_PATTERN.search(f"{route_name} {route_path}"))


def _route_has_auth_marker(route: dict[str, Any], symbol_index: dict[tuple, dict]) -> bool:
    if route.get("has_auth_dependency"):
        return True
    identity = (route.get("name"), route.get("line"), route.get("scope"))
    symbol = symbol_index.get(identity, {})
    return any(AUTH_MARKER_PATTERN.search(decorator) for decorator in symbol.get("decorators", []))


def _evidence_symbols_for_finding(finding: dict[str, Any], metadata: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only the AST symbol directly associated with a finding's source line."""
    symbols = metadata.get("symbols", [])
    line = int(finding.get("line") or 0)
    if not line:
        return []

    if finding.get("type") == "route_without_detected_auth_dependency":
        route = next((
            item for item in metadata.get("routes", [])
            if int(item.get("line") or 0) == line
        ), None)
        if route:
            exact = [
                symbol for symbol in symbols
                if symbol.get("kind") == "function"
                and symbol.get("name") == route.get("name")
                and symbol.get("line") == route.get("line")
                and symbol.get("scope") == route.get("scope")
            ]
            if exact:
                return [_evidence_symbol(symbol, line) for symbol in exact]

    containing = [
        symbol for symbol in symbols
        if int(symbol.get("line") or 0) <= line <= int(symbol.get("end_line") or symbol.get("line") or 0)
    ]
    if not containing:
        return []

    # Nested methods/functions are more precise than their enclosing class/module.
    smallest_span = min(
        int(symbol.get("end_line") or symbol.get("line") or 0) - int(symbol.get("line") or 0)
        for symbol in containing
    )
    precise = [
        symbol for symbol in containing
        if int(symbol.get("end_line") or symbol.get("line") or 0) - int(symbol.get("line") or 0) == smallest_span
    ]
    return [_evidence_symbol(symbol, line) for symbol in precise]


def _evidence_symbol(symbol: dict[str, Any], finding_line: int) -> dict[str, Any]:
    """Keep the symbol identity and both its definition and violating line."""
    return {
        "kind": symbol.get("kind", "symbol"),
        "name": symbol.get("name", ""),
        "line": symbol.get("line"),
        "finding_line": finding_line,
        "scope": symbol.get("scope"),
    }


def _attach_finding_evidence(findings: list[dict[str, Any]], file_metadata: dict[str, dict[str, Any]]) -> None:
    """Attach rule-scoped symbols and preserve complete file inventory separately."""
    evidence_by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for finding in findings:
        metadata = file_metadata.get(finding["file"], {})
        evidence = _evidence_symbols_for_finding(finding, metadata)
        finding["evidence_symbols"] = evidence
        evidence_by_file[finding["file"]].extend(evidence)

    for file_path, metadata in file_metadata.items():
        metadata.setdefault("file_symbols", metadata.get("symbols", []))
        unique: dict[tuple[Any, ...], dict[str, Any]] = {}
        for symbol in evidence_by_file.get(file_path, []):
            key = (symbol.get("kind"), symbol.get("name"), symbol.get("line"), symbol.get("finding_line"), symbol.get("scope"))
            unique.setdefault(key, symbol)
        metadata["evidence_symbols"] = list(unique.values())


def _empty_file_metadata(path: str, line_count: int, file_type: str = "source") -> dict[str, Any]:
    return {
        "file_type": file_type,
        "classes": [],
        "functions": [],
        "imports": [],
        "import_evidence": [],
        "symbols": [],
        "routes": [],
        "line_count": line_count,
        "classification": "source",
        "classifications": ["source"],
        "internal_imports": [],
        "external_imports": [],
        "security_warnings": [],
        "heuristics": [],
    }


def scan_security_findings(repo_path: str, file_metadata: dict | None = None) -> list[dict[str, Any]]:
    """Scan repository text, Python AST settings, and route auth metadata."""
    root = Path(repo_path)
    findings: list[dict[str, Any]] = []
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(root)
        if _skip_path(relative) or not _is_scannable(path):
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        findings.extend(_source_findings(relative.as_posix(), source))

    for file_path, metadata in (file_metadata or {}).items():
        if not isinstance(metadata, dict) or metadata.get("error"):
            continue
        symbol_index = {
            (symbol.get("name"), symbol.get("line"), symbol.get("scope")): symbol
            for symbol in metadata.get("symbols", [])
        }
        for route in metadata.get("routes", []):
            if _route_auth_expected(route) and not _route_has_auth_marker(route, symbol_index):
                findings.append(_line_finding(
                    file_path,
                    int(route.get("line", 1)),
                    "route_without_detected_auth_dependency",
                    "review",
                    "This endpoint appears to handle a write or sensitive resource, but no auth marker was detected.",
                ))

    unique: dict[tuple[str, int, str], dict[str, Any]] = {}
    for finding in findings:
        key = (finding["file"], finding["line"], finding["type"])
        unique.setdefault(key, finding)
    return sorted(unique.values(), key=lambda item: (item["file"], item["line"], item["type"]))


def scan_repository_security(repo_path: str, file_metadata: dict[str, dict]) -> dict[str, Any]:
    """Attach per-file warnings and infrastructure/config roles to graph metadata."""
    root = Path(repo_path)
    container_files = detect_containers(repo_path)
    findings = scan_security_findings(repo_path, file_metadata)
    _attach_finding_evidence(findings, file_metadata)
    findings_by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for finding in findings:
        findings_by_file[finding["file"]].append(finding)

    for file_path in findings_by_file:
        if file_path not in file_metadata:
            try:
                line_count = len((root / file_path).read_text(encoding="utf-8").splitlines())
            except (OSError, UnicodeError):
                line_count = 0
            file_metadata[file_path] = _empty_file_metadata(file_path, line_count)

    for file_path, metadata in file_metadata.items():
        metadata.setdefault("security_warnings", [])
        metadata["security_warnings"].extend(findings_by_file.get(file_path, []))
        metadata.setdefault("file_symbols", metadata.get("symbols", []))
        metadata.setdefault("evidence_symbols", [])
        metadata.setdefault("heuristics", [])

    for infrastructure_file in container_files:
        file_path = infrastructure_file["file"]
        try:
            line_count = len((root / file_path).read_text(encoding="utf-8").splitlines())
        except (OSError, UnicodeError):
            line_count = 0
        metadata = file_metadata.setdefault(
            file_path,
            _empty_file_metadata(file_path, line_count, "configuration"),
        )
        role = infrastructure_file["role"]
        metadata["file_type"] = "infrastructure" if role == "infrastructure" else "configuration"
        metadata["classification"] = role
        metadata["classifications"] = [role]
        heuristic = {
            "type": "infrastructure_file",
            "role": role,
            "kind": infrastructure_file["kind"],
        }
        if heuristic not in metadata["heuristics"]:
            metadata["heuristics"].append(heuristic)

    return {"container_files": container_files, "security_findings": findings}
