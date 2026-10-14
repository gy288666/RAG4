"""Explicit operator worker. No queue and no index activation side effects."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description="Execute retained research task checkpoints")
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--steps", type=int, default=1, choices=range(1, 25))
    args = parser.parse_args()
    if not os.environ.get("DATABASE_URL"):
        parser.error("Set DATABASE_URL explicitly; the worker never chooses a database")
    from app.research.runtime import configured_agent
    agent = configured_agent()
    try:
        for _ in range(args.steps):
            task = agent.step(args.user_id, args.task_id)
            print(json.dumps({"task_id": task.id, "status": task.status, "revision": task.revision,
                "tool_calls_used": task.tool_calls_used, "model_calls_reserved": task.model_calls_used,
                "error_code": task.error_code}, ensure_ascii=True))
            if task.status in {"completed", "paused", "cancelled", "failed"}:
                return 0 if task.status == "completed" else 2
        return 0
    except Exception as error:
        print(json.dumps({"status": "worker_error", "error_type": type(error).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
