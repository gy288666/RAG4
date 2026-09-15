"""Evaluate ranked evidence IDs with Recall@K, MRR@K and nDCG@K."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Iterable


def reciprocal_rank(relevant: set[str], ranked: list[str], k: int) -> float:
    for position, item_id in enumerate(ranked[:k], start=1):
        if item_id in relevant:
            return 1.0 / position
    return 0.0


def ndcg(relevant: set[str], ranked: list[str], k: int) -> float:
    dcg = sum(
        1.0 / math.log2(position + 1)
        for position, item_id in enumerate(ranked[:k], start=1)
        if item_id in relevant
    )
    ideal_count = min(len(relevant), k)
    ideal = sum(1.0 / math.log2(position + 1) for position in range(1, ideal_count + 1))
    return dcg / ideal if ideal else 0.0


def evaluate(rows: Iterable[dict[str, Any]], ks: list[int]) -> dict[str, Any]:
    totals = {k: {"recall": 0.0, "mrr": 0.0, "ndcg": 0.0} for k in ks}
    count = 0
    for row in rows:
        relevant = {str(value) for value in row.get("relevant_ids", [])}
        ranked = [str(value) for value in row.get("ranked_ids", [])]
        if not relevant:
            continue
        count += 1
        for k in ks:
            found = len(relevant.intersection(ranked[:k]))
            totals[k]["recall"] += found / len(relevant)
            totals[k]["mrr"] += reciprocal_rank(relevant, ranked, k)
            totals[k]["ndcg"] += ndcg(relevant, ranked, k)
    if count == 0:
        raise ValueError("没有包含 relevant_ids 的有效评测记录")
    return {
        "queries": count,
        "metrics": {
            f"@{k}": {name: round(value / count, 6) for name, value in values.items()}
            for k, values in totals.items()
        },
    }


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--k", type=int, nargs="+", default=[1, 5, 10])
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ks = sorted({value for value in args.k if value > 0})
    if not ks:
        raise SystemExit("--k 至少需要一个正整数")
    result = evaluate(read_jsonl(args.input), ks)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    print(payload)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
