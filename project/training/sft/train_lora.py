"""LoRA-SFT entry point for graph extraction or cited artifact composition."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-data", type=Path, required=True)
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--epochs", type=float, default=2.0)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--max-seq-length", type=int, default=4096)
    parser.add_argument("--lora-rank", type=int, default=16)
    parser.add_argument("--fp16", action="store_true")
    return parser.parse_args()


def read_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict) or not (row.get("messages") or row.get("text")):
                raise ValueError(f"{path}:{line_number} 需要 messages 或 text")
            rows.append(row)
    if not rows:
        raise ValueError("训练集为空")
    return rows


def main() -> None:
    args = parse_args()
    from datasets import Dataset
    from peft import LoraConfig, TaskType
    from transformers import AutoTokenizer
    from trl import SFTConfig, SFTTrainer

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, use_fast=True)
    formatted: list[dict[str, str]] = []
    for row in read_rows(args.train_data):
        text = row.get("text")
        if not text:
            text = tokenizer.apply_chat_template(
                row["messages"], tokenize=False, add_generation_prompt=False
            )
        formatted.append({"text": str(text)})

    config = SFTConfig(
        output_dir=str(args.output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate,
        max_seq_length=args.max_seq_length,
        fp16=args.fp16,
        save_strategy="epoch",
        logging_steps=5,
        report_to="none",
    )
    trainer = SFTTrainer(
        model=args.base_model,
        args=config,
        train_dataset=Dataset.from_list(formatted),
        processing_class=tokenizer,
        peft_config=LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=args.lora_rank,
            lora_alpha=args.lora_rank * 2,
            lora_dropout=0.05,
            target_modules="all-linear",
        ),
    )
    trainer.train()
    trainer.save_model(str(args.output_dir))


if __name__ == "__main__":
    main()
