"""Freeze or grade the literature pilot offline; never executes model calls."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.evaluation.acceptance import Review, Submission, prepare, score


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--answers", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="Must not already exist")
    args = parser.parse_args(argv)
    submission = None if args.answers is None else Submission.model_validate_json(args.answers.read_bytes())
    pack, template = prepare(args.pilot, args.sources, submission)
    review = template if args.review is None else Review.model_validate_json(args.review.read_bytes())
    result = score(pack, review)
    args.output.mkdir(parents=True, exist_ok=False)
    for name, value in (("pack", pack), ("review", review.model_dump(mode="json")), ("report", result)):
        (args.output / f"{name}.json").write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["subgate_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
