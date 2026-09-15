"""Build Embedding, Reranker and evaluation JSONL from judged retrieval candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number} 不是合法 JSON") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} 必须是 JSON object")
            yield value


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def build_rows(
    records: Iterable[dict[str, Any]], max_negatives: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    embedding_rows: list[dict[str, Any]] = []
    reranker_rows: list[dict[str, Any]] = []
    evaluation_rows: list[dict[str, Any]] = []

    for record in records:
        query_id = str(record.get("query_id", "")).strip()
        query = str(record.get("query", "")).strip()
        candidates = record.get("candidates")
        if not query_id or not query or not isinstance(candidates, list):
            raise ValueError("每行都必须包含非空 query_id、query 和 candidates 数组")

        valid = [
            item
            for item in candidates
            if isinstance(item, dict)
            and str(item.get("id", "")).strip()
            and str(item.get("text", "")).strip()
        ]
        positives = [item for item in valid if item.get("label") is True]
        negatives = [item for item in valid if item.get("label") is False]
        negatives.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
        negatives = negatives[:max_negatives]
        if not positives or not negatives:
            raise ValueError(f"{query_id} 至少需要一个正例和一个负例")

        for positive in positives:
            for negative in negatives:
                embedding_rows.append(
                    {
                        "query_id": query_id,
                        "anchor": query,
                        "positive": str(positive["text"]),
                        "negative": str(negative["text"]),
                    }
                )

        for item in positives + negatives:
            reranker_rows.append(
                {
                    "query_id": query_id,
                    "query": query,
                    "passage": str(item["text"]),
                    "label": 1.0 if item.get("label") is True else 0.0,
                }
            )

        ranked = sorted(valid, key=lambda item: float(item.get("score", 0.0)), reverse=True)
        evaluation_rows.append(
            {
                "query_id": query_id,
                "relevant_ids": [str(item["id"]) for item in positives],
                "ranked_ids": [str(item["id"]) for item in ranked],
            }
        )

    return embedding_rows, reranker_rows, evaluation_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-negatives", type=int, default=4)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.max_negatives < 1:
        raise SystemExit("--max-negatives 必须大于 0")
    embedding, reranker, evaluation = build_rows(read_jsonl(args.input), args.max_negatives)
    counts = {
        "embedding_train": write_jsonl(args.output_dir / "embedding_train.jsonl", embedding),
        "reranker_train": write_jsonl(args.output_dir / "reranker_train.jsonl", reranker),
        "ranking_eval": write_jsonl(args.output_dir / "ranking_eval.jsonl", evaluation),
    }
    print(json.dumps(counts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
