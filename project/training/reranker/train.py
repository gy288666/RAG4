"""Fine-tune a CrossEncoder reranker from labeled query/passage pairs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-data", type=Path, required=True)
    parser.add_argument("--base-model", default="BAAI/bge-reranker-base")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--epochs", type=float, default=2.0)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--warmup-ratio", type=float, default=0.1)
    parser.add_argument("--lora-rank", type=int, default=0, help="0 表示全量微调")
    parser.add_argument("--fp16", action="store_true")
    return parser.parse_args()


def load_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not str(row.get("query", "")).strip() or not str(row.get("passage", "")).strip():
                raise ValueError(f"{path}:{line_number} 缺少 query/passage")
            label = float(row.get("label"))
            if label not in {0.0, 1.0}:
                raise ValueError(f"{path}:{line_number} label 必须是 0 或 1")
            rows.append({"query": str(row["query"]), "passage": str(row["passage"]), "label": label})
    if not rows:
        raise ValueError("训练集为空")
    return rows


def add_lora(model, rank: int) -> None:
    from peft import LoraConfig, TaskType

    model.add_adapter(
        LoraConfig(
            task_type=TaskType.SEQ_CLS,
            inference_mode=False,
            r=rank,
            lora_alpha=rank * 2,
            lora_dropout=0.05,
        ),
    )


def main() -> None:
    args = parse_args()
    from datasets import Dataset
    from sentence_transformers import CrossEncoder
    from sentence_transformers.cross_encoder import (
        CrossEncoderTrainer,
        CrossEncoderTrainingArguments,
    )
    from sentence_transformers.cross_encoder.losses import BinaryCrossEntropyLoss

    model = CrossEncoder(args.base_model, num_labels=1)
    if args.lora_rank > 0:
        add_lora(model, args.lora_rank)

    training_args = CrossEncoderTrainingArguments(
        output_dir=str(args.output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        warmup_ratio=args.warmup_ratio,
        fp16=args.fp16,
        save_strategy="epoch",
        logging_steps=10,
        report_to="none",
    )
    trainer = CrossEncoderTrainer(
        model=model,
        args=training_args,
        train_dataset=Dataset.from_list(load_rows(args.train_data)),
        loss=BinaryCrossEntropyLoss(model),
    )
    trainer.train()
    model.save_pretrained(str(args.output_dir))


if __name__ == "__main__":
    main()
