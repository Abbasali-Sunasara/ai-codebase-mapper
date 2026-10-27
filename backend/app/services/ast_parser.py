import os
import ast
import networkx as nx
from typing import Dict, Any, List

class CodebaseASTParser(ast.NodeVisitor):
    """
    Parses Python source files using AST to extract functions, classes, 
    and imports, building a NetworkX structural graph.
    """
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.classes: List[str] = []
        self.functions: List[str] = []
        self.imports: List[str] = []

    def visit_ClassDef(self, node: ast.ClassDef):
        self.classes.append(node.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self.functions.append(node.name)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            self.imports.append(node.module)
        self.generic_visit(node)


def analyze_repository_ast(repo_path: str) -> Dict[str, Any]:
    """
    Scans the cloned repository directory, parses all Python files,
    and constructs a NetworkX graph representing the codebase structure.
    """
    graph = nx.DiGraph()
    file_metadata = {}

    # Walk through the repository directory
    for root, _, files in os.walk(repo_path):
        # Skip hidden directories like .git or venv
        if any(part.startswith('.') for part in root.split(os.sep)):
            continue

        for file in files:
            if file.endswith(".py"):
                full_path = os.path.join(root, file)
                relative_path = os.path.relpath(full_path, repo_path)

                # Add file as a node in the graph
                graph.add_node(relative_path, type="file")

                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read(), filename=full_path)
                    
                    parser = CodebaseASTParser(relative_path)
                    parser.visit(tree)

                    # Store metadata
                    file_metadata[relative_path] = {
                        "classes": parser.classes,
                        "functions": parser.functions,
                        "imports": parser.imports
                    }

                    # Add import edges to graph
                    for imp in parser.imports:
                        # Add edge showing dependency relationship
                        graph.add_edge(relative_path, imp, relationship="imports")

                except Exception as e:
                    # Log parsing errors gracefully without crashing the whole scan
                    file_metadata[relative_path] = {"error": str(e)}

    return {
        "nodes_count": graph.number_of_nodes(),
        "edges_count": graph.number_of_edges(),
        "file_metadata": file_metadata,
        "graph_summary": list(graph.nodes(data=True))[:20]  # Preview first 20 nodes
    }