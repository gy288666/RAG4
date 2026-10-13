"""Read-only MySQL Phase 2 gate. Password is read from an environment variable."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3307)
    parser.add_argument("--user", default="root")
    args = parser.parse_args()
    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL
    from app.services.schema_preflight import inspect_schema

    password = os.environ.get("RAG4_TEST_MYSQL_PASSWORD")
    if password is None:
        print(json.dumps({"error": "missing_password_environment"}))
        return 2
    engine = create_engine(URL.create("mysql+pymysql", username=args.user, password=password,
                           host=args.host, port=args.port, database=args.database),
                           connect_args={"connect_timeout": 10, "read_timeout": 15})
    try:
        report = inspect_schema(engine)
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 0 if report.ready else 1
    except Exception as error:
        # Driver messages may contain connection details; never emit them.
        print(json.dumps({"error": "inspection_failed", "error_type": type(error).__name__}))
        return 2
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
