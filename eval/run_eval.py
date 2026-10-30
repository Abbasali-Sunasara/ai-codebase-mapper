"""Compare one JSON prediction file with its hand-labeled ground truth.

Both files use {"components": [...], "edges": [...]} where edges are objects
with `source` and `target` fields. Component values should be stable file:line
identifiers produced by the analyzer.
"""

import argparse
import json
from pathlib import Path


def precision_recall(predicted: set, expected: set) -> dict[str, float]:
    true_positives = len(predicted & expected)
    precision = true_positives / len(predicted) if predicted else 0.0
    recall = true_positives / len(expected) if expected else 0.0
    return {"precision": precision, "recall": recall}


def load_labels(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def edge_set(items: list[dict]) -> set[tuple[str, str]]:
    return {(item["source"], item["target"]) for item in items}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("predictions", type=Path)
    parser.add_argument("ground_truth", type=Path)
    args = parser.parse_args()
    predicted, expected = load_labels(args.predictions), load_labels(args.ground_truth)
    report = {
        "components": precision_recall(set(predicted.get("components", [])), set(expected.get("components", []))),
        "edges": precision_recall(edge_set(predicted.get("edges", [])), edge_set(expected.get("edges", []))),
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
