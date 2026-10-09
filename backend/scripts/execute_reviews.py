"""Thin command-line entry point for explicit human review execution."""

import argparse
from pathlib import Path

from competition_copilot.ingestion.review_executor import (
    ReviewExecutionError,
    execute_review_file,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect or execute a review manifest")
    parser.add_argument("manifest", type=Path, help="Human Review Manifest JSON path")
    parser.add_argument(
        "--execute", action="store_true", help="Run explicit decisions and write Seeds"
    )
    args = parser.parse_args(argv)
    try:
        report = execute_review_file(
            args.manifest, PROJECT_ROOT, execute=args.execute
        )
    except ReviewExecutionError as exc:
        print(f"{exc.code}: {exc}")
        return 1
    print("Mode:", "execute" if args.execute else "dry-run")
    for entry in report.entries:
        detail = f" {entry.code}: {entry.message}" if entry.code else ""
        seed = f" seed={entry.seed_path}" if entry.seed_path else ""
        print(f"{entry.raw_fixture_path}: {entry.status}{seed}{detail}")
    print("Summary:", " ".join(f"{key}={value}" for key, value in report.summary.items()))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
