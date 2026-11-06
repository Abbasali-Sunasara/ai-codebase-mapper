"""Tree-sitter parser routing for supported non-Python source files.

Python deliberately stays in ``ast_parser`` and uses Python's native ``ast``.
This module only handles JavaScript/TypeScript, C/C++, and Java.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from app.services.classifier import classify_file, classify_file_roles


EXTENSION_LANGUAGES = {
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".java": "java",
}


def language_for_path(path: str) -> str | None:
    """Return the supported parser language for a source path."""
    return EXTENSION_LANGUAGES.get(PurePosixPath(path).suffix.lower())


def _load_language(language: str):
    """Load a tree-sitter Language across supported grammar package APIs."""
    from tree_sitter import Language

    if language == "javascript":
        import tree_sitter_javascript as grammar
        capsule = grammar.language()
    elif language in {"typescript", "tsx"}:
        import tree_sitter_typescript as grammar
        capsule = grammar.language_tsx() if language == "tsx" else grammar.language_typescript()
    elif language == "c":
        import tree_sitter_c as grammar
        capsule = grammar.language()
    elif language == "cpp":
        import tree_sitter_cpp as grammar
        capsule = grammar.language()
    else:
        import tree_sitter_java as grammar
        capsule = grammar.language()
    return Language(capsule)


def _parser_for(language: str):
    from tree_sitter import Parser

    grammar_language = _load_language(language)
    try:
        return Parser(grammar_language)
    except TypeError:  # Compatibility with tree-sitter 0.21's constructor.
        parser = Parser()
        parser.set_language(grammar_language)
        return parser


def _text(node: Any, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _field_name(node: Any, source: bytes) -> str | None:
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return _text(name_node, source).strip().strip("`\"'")
    # Declarators and some grammar versions expose the identifier as a child.
    for child in node.children:
        if child.type in {"identifier", "property_identifier", "type_identifier", "field_identifier"}:
            return _text(child, source).strip().strip("`\"'")
    return None


def _function_name(node: Any, source: bytes) -> str | None:
    name = _field_name(node, source)
    if name:
        return name
    declarator = node.child_by_field_name("declarator")
    while declarator is not None:
        if declarator.type in {"identifier", "field_identifier", "operator_name"}:
            return _text(declarator, source).strip()
        nested = declarator.child_by_field_name("declarator")
        if nested is not None:
            declarator = nested
            continue
        # Qualified C++ function declarators can wrap the final identifier.
        identifiers = [
            child for child in declarator.children
            if child.type in {"identifier", "field_identifier", "operator_name"}
        ]
        if identifiers:
            return _text(identifiers[-1], source).strip()
        declarator = next((
            child for child in declarator.children
            if child.type in {"function_declarator", "pointer_declarator", "reference_declarator", "qualified_identifier"}
        ), None)
    return None


CLASS_NODES = {
    "class_declaration", "abstract_class_declaration", "class_specifier",
    "struct_specifier", "union_specifier", "interface_declaration",
    "enum_declaration", "record_declaration", "annotation_type_declaration",
}
FUNCTION_NODES = {
    "function_declaration", "generator_function_declaration", "method_definition",
    "method_declaration", "constructor_declaration", "function_definition",
    "function_item", "abstract_method_declaration",
}
IMPORT_NODES = {
    "import_statement", "import_declaration", "preproc_include", "using_declaration",
    "export_statement", "export_declaration",
}


def parse_tree_sitter_file(relative_path: str, source_text: str) -> dict[str, Any]:
    """Parse a supported source file and return graph/cache-compatible metadata."""
    language = language_for_path(relative_path)
    if language is None:
        raise ValueError(f"No tree-sitter parser is configured for {relative_path}")

    source = source_text.encode("utf-8")
    tree = _parser_for(language).parse(source)
    classes: list[str] = []
    functions: list[str] = []
    imports: list[str] = []
    import_evidence: list[dict[str, Any]] = []
    symbols: list[dict[str, Any]] = []
    exports_or_includes: list[str] = []
    class_lines: list[int] = []
    function_lines: list[int] = []
    import_lines: list[int] = []
    export_lines: list[int] = []

    def visit(node: Any, scope: list[str]) -> None:
        node_type = node.type
        line = node.start_point.row + 1
        next_scope = scope

        if node_type in CLASS_NODES:
            name = _field_name(node, source)
            if name:
                classes.append(name)
                class_lines.append(line)
                symbols.append({
                    "kind": "class", "name": name, "line": line,
                    "end_line": node.end_point.row + 1, "scope": ".".join(scope) or None,
                    "decorators": [], "bases": [], "fields": [],
                })
                next_scope = [*scope, name]

        elif node_type in FUNCTION_NODES:
            name = _function_name(node, source)
            if name:
                functions.append(name)
                function_lines.append(line)
                symbols.append({
                    "kind": "function", "name": name, "line": line,
                    "end_line": node.end_point.row + 1, "scope": ".".join(scope) or None,
                    "arguments": [], "decorators": [],
                })
                next_scope = [*scope, name]

        # Include common assigned-arrow/function-expression symbols in JS/TS.
        elif language in {"javascript", "typescript", "tsx"} and node_type in {"variable_declarator", "lexical_declaration", "variable_declaration"}:
            value = node.child_by_field_name("value") if node_type == "variable_declarator" else None
            if value is not None and value.type in {"arrow_function", "function_expression", "generator_function"}:
                name = _field_name(node, source)
                if name:
                    functions.append(name)
                    function_lines.append(line)
                    symbols.append({
                        "kind": "function", "name": name, "line": line,
                        "end_line": node.end_point.row + 1, "scope": ".".join(scope) or None,
                        "arguments": [], "decorators": [],
                    })

        if node_type in IMPORT_NODES:
            raw_import = _text(node, source).strip()
            module = _import_target(node, raw_import, source, language)
            if module:
                imports.append(module)
                import_evidence.append({"module": module, "line": line, "kind": "include" if language in {"c", "cpp"} else "import"})
                import_lines.append(line)
            if node_type in {"preproc_include", "export_statement", "export_declaration"}:
                exports_or_includes.append(raw_import)
                export_lines.append(line)

        for child in node.children:
            visit(child, next_scope)

    visit(tree.root_node, [])
    # Keep source-order stable and avoid duplicate names/edges from nested grammar nodes.
    imports = list(dict.fromkeys(imports))
    for symbol in symbols:
        symbol["classification"] = classify_file(relative_path, [symbol])
        symbol["classifications"] = classify_file_roles(relative_path, [symbol])
    metadata = {
        "file_path": relative_path,
        "file_type": language,
        "parser_language": language,
        "classes": classes,
        "functions": functions,
        "imports": imports,
        "import_evidence": import_evidence,
        "exports_or_includes": exports_or_includes,
        "line_numbers": {
            "classes": list(dict.fromkeys(class_lines)),
            "functions": list(dict.fromkeys(function_lines)),
            "imports": list(dict.fromkeys(import_lines)),
            "exports_or_includes": list(dict.fromkeys(export_lines)),
        },
        "symbols": symbols,
        "routes": [],
        "line_count": len(source_text.splitlines()),
        "classification": classify_file(relative_path, symbols),
        "classifications": classify_file_roles(relative_path, symbols),
    }
    metadata["file_symbols"] = symbols
    return metadata


def _import_target(node: Any, raw: str, source: bytes, language: str) -> str | None:
    if language in {"c", "cpp"}:
        for child in node.children:
            if child.type in {"string_literal", "system_lib_string"}:
                return _text(child, source).strip().strip('<>"')
        return None
    if language == "java":
        return raw.removeprefix("import").removesuffix(";").strip().removeprefix("static ") or None
    # JS/TS source string is the module specifier; retain its raw specifier so
    # the graph builder can resolve relative imports without executing code.
    for child in node.children:
        if child.type in {"string", "string_literal", "template_string"}:
            return _text(child, source).strip().strip("`\"'")
    return None

