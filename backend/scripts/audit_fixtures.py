"""Display the read-only batch fixture audit from the command line."""

import argparse
from pathlib import Path

from competition_copilot.ingestion.batch_audit import BatchAuditReport, audit_fixtures

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _table(report: BatchAuditReport) -> str:
    rows = [
        (
            item.fixture_path,
            item.raw_load_status,
            item.normalization_status,
            str(item.validation_error_count),
            str(item.validation_warning_count),
            str(item.track_count) if item.track_count is not None else "-",
            item.registration_window_state or "-",
            item.competition_window_state or "-",
            item.seed_status,
        )
        for item in report.fixtures
    ]
    headers = (
        "Fixture",
        "Raw",
        "Normalize",
        "Errors",
        "Warnings",
        "Tracks",
        "RegWindow",
        "CompWindow",
        "Seed",
    )
    widths = [max(len(row[index]) for row in [headers, *rows]) for index in range(9)]

    def format_row(row: tuple[str, ...]) -> str:
        return "  ".join(value.ljust(width) for value, width in zip(row, widths, strict=True))

    return "\n".join(
        [format_row(headers), format_row(tuple("-" * width for width in widths))]
        + [format_row(row) for row in rows]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Raw fixtures and existing Seeds")
    parser.add_argument("--raw-dir", type=Path, default=PROJECT_ROOT / "data/raw")
    parser.add_argument("--seed-dir", type=Path, default=PROJECT_ROOT / "data/seed")
    args = parser.parse_args(argv)
    report = audit_fixtures(args.raw_dir, args.seed_dir)
    print(_table(report))

    summary = report.summary
    print(
        "\nSummary: "
        f"raw={summary.total_raw_fixtures} "
        f"load_passed={summary.raw_load_passed} "
        f"load_failed={summary.raw_load_failed} "
        f"normalized={summary.normalization_passed} "
        f"normalization_failed={summary.normalization_failed} "
        f"errors={summary.validation_errors} "
        f"warnings={summary.validation_warnings} "
        f"seeds={summary.existing_seeds} "
        f"seed_passed={summary.seed_passed} "
        f"seed_failed={summary.seed_failed} "
        f"id_collisions={summary.id_collisions}"
    )
    for finding in report.findings:
        print(f"{finding.code}: {finding.path}: {finding.message}")
    for fixture in report.fixtures:
        for finding in fixture.findings:
            print(f"{finding.code}: {finding.path}: {finding.message}")
        for issue in fixture.validation_issues:
            print(f"{issue.severity.value}: {fixture.fixture_path}: {issue.code}: {issue.message}")
    for seed in report.seeds:
        for finding in seed.findings:
            print(f"{finding.code}: {finding.path}: {finding.message}")
    for collision in report.id_collisions:
        print(
            f"{collision.code}: {collision.identifier}: "
            + ", ".join(collision.fixture_paths)
        )
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
