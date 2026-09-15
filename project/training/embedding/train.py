"""Fine-tune a Sentence Transformer with query/positive/hard-negative triplets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-data", type=Path, required=True)
    parser.add_argument("--base-model", default="BAAI/bge-small-zh-v1.5")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--epochs", type=float, default=2.0)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--warmup-ratio", type=float, default=0.1)
    parser.add_argument("--lora-rank", type=int, default=0, help="0 表示全量微调")
    parser.add_argument("--fp16", action="store_true")
    return parser.parse_args()


def load_rows(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not all(str(row.get(key, "")).strip() for key in ("anchor", "positive", "negative")):
                raise ValueError(f"{path}:{line_number} 缺少 anchor/positive/negative")
            rows.append({key: str(row[key]) for key in ("anchor", "positive", "negative")})
    if not rows:
        raise ValueError("训练集为空")
    return rows


def add_lora(model, rank: int) -> None:
    from peft import LoraConfig, TaskType

    model.add_adapter(
        LoraConfig(
            task_type=TaskType.FEATURE_EXTRACTION,
            inference_mode=False,
            r=rank,
            lora_alpha=rank * 2,
            lora_dropout=0.05,
        ),
    )


def main() -> None:
    args = parse_args()
    from datasets import Dataset
    from sentence_transformers import (
        SentenceTransformer,
        SentenceTransformerTrainer,
        SentenceTransformerTrainingArguments,
    )
    from sentence_transformers.losses import MultipleNegativesRankingLoss

    model = SentenceTransformer(args.base_model)
    if args.lora_rank > 0:
        add_lora(model, args.lora_rank)

    dataset = Dataset.from_list(load_rows(args.train_data))
    training_args = SentenceTransformerTrainingArguments(
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
    trainer = SentenceTransformerTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        loss=MultipleNegativesRankingLoss(model),
    )
    trainer.train()
    model.save_pretrained(str(args.output_dir))


if __name__ == "__main__":
    main()
