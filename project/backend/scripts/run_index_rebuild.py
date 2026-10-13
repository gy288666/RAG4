"""Run ONE existing rebuild with configured credentials; never initialize/migrate DB."""
import argparse
import json
import os
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True, type=int)
    parser.add_argument("--task-id", required=True)
    args = parser.parse_args()
    # Avoid silently using the historical default database on an operator typo.
    if not os.environ.get("DATABASE_URL"):
        print(json.dumps({"status": "rejected", "error_code": "explicit_database_required"}))
        return 2
    started = perf_counter()
    try:
        from app.services.rebuild_execution import execute_configured_rebuild
        task = execute_configured_rebuild(args.user_id, args.task_id)
        report = {"task_id": task.id, "status": task.status, "attempt": task.attempt,
                  "version_id": task.version_id, "error_code": task.error_code,
                  "duration_ms": task.duration_ms}
        code = 0 if task.status == "ready" else 1
    except Exception as error:
        # Never emit driver/model exceptions containing URLs, keys or file paths.
        report = {"status": "rejected", "error_code": type(error).__name__}
        code = 2
    report["worker_duration_ms"] = round((perf_counter() - started) * 1000)
    print(json.dumps(report))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
