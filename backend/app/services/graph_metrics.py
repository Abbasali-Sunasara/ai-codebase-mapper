import networkx as nx


OVERSIZED_MODULE_LINE_THRESHOLD = 500
MAX_REPORTED_CYCLES = 100


def _canonical_cycle(cycle: list[str]) -> list[str]:
    """Rotate a directed cycle to a stable starting module without reversing it."""
    if not cycle:
        return []
    rotations = [tuple(cycle[index:] + cycle[:index]) for index in range(len(cycle))]
    return list(min(rotations))


def _line_count(node: dict) -> int:
    try:
        return int(node.get("line_count", 0))
    except (TypeError, ValueError):
        return 0


def calculate_graph_metrics(nodes: list[dict], edges: list[dict]) -> dict:
    """Compute module fan, import cycles, and large-file metrics.

    Import edges point from the importing module to its imported dependency.
    Therefore fan-in is the number of incoming import edges (other modules
    depending on this module), and fan-out is the number of outgoing edges
    (dependencies this module imports). Repeated imports between the same pair
    count once because these metrics describe module dependencies, not statements.
    """
    modules = {
        node["id"]: node
        for node in nodes
        if isinstance(node, dict) and isinstance(node.get("id"), str) and node["id"]
    }
    module_ids = set(modules)
    graph = nx.DiGraph()
    graph.add_nodes_from(sorted(module_ids))

    valid_edges = {
        (edge.get("source"), edge.get("target"))
        for edge in edges
        if isinstance(edge, dict)
        and edge.get("type") in (None, "imports")
        and isinstance(edge.get("source"), str)
        and isinstance(edge.get("target"), str)
        and edge.get("source") in module_ids
        and edge.get("target") in module_ids
    }
    graph.add_edges_from(sorted(valid_edges))

    fan = {
        module_id: {
            "fan_in": graph.in_degree(module_id),
            "fan_out": graph.out_degree(module_id),
        }
        for module_id in sorted(graph.nodes)
    }

    cycles: list[list[str]] = []
    cycle_iterator = nx.simple_cycles(graph)
    cycles_truncated = False
    for cycle in cycle_iterator:
        cycles.append(_canonical_cycle(cycle))
        if len(cycles) == MAX_REPORTED_CYCLES:
            cycles_truncated = next(cycle_iterator, None) is not None
            break
    cycles.sort()

    oversized_modules = sorted(
        module_id
        for module_id, node in modules.items()
        if _line_count(node) >= OVERSIZED_MODULE_LINE_THRESHOLD
    )

    return {
        "cycles": cycles,
        "cycles_truncated": cycles_truncated,
        "fan": fan,
        "oversized_modules": oversized_modules,
    }


def summarize_graph(graph: nx.DiGraph) -> dict[str, int]:
    return {"nodes_count": graph.number_of_nodes(), "edges_count": graph.number_of_edges()}
