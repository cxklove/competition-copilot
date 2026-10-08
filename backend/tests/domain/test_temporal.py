from datetime import datetime, timedelta, timezone, tzinfo

import pytest
from pydantic import ValidationError

from competition_copilot.domain.temporal import TimeWindow


def test_both_values_omitted() -> None:
    window = TimeWindow()

    assert window.start_at is None
    assert window.end_at is None


def test_only_start_at() -> None:
    start_at = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
    window = TimeWindow(start_at=start_at)

    assert window.start_at == start_at
    assert window.end_at is None


def test_only_end_at() -> None:
    end_at = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)
    window = TimeWindow(end_at=end_at)

    assert window.start_at is None
    assert window.end_at == end_at


def test_start_before_end() -> None:
    start_at = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
    end_at = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)

    assert TimeWindow(start_at=start_at, end_at=end_at).end_at == end_at


def test_equal_start_and_end() -> None:
    instant = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)

    assert TimeWindow(start_at=instant, end_at=instant).start_at == instant


def test_start_after_end_is_rejected() -> None:
    with pytest.raises(ValidationError, match="start_at must be before"):
        TimeWindow(
            start_at=datetime(2026, 10, 9, 12, tzinfo=timezone.utc),
            end_at=datetime(2026, 10, 8, 12, tzinfo=timezone.utc),
        )


def test_naive_start_is_rejected() -> None:
    with pytest.raises(ValidationError, match="start_at"):
        TimeWindow(start_at=datetime(2026, 10, 8, 12))


def test_naive_end_is_rejected() -> None:
    with pytest.raises(ValidationError, match="end_at"):
        TimeWindow(end_at=datetime(2026, 10, 8, 12))


def test_utc_datetime_is_accepted() -> None:
    start_at = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
    window = TimeWindow(start_at=start_at)

    assert window.start_at == start_at
    assert window.start_at.utcoffset() == timedelta(0)


def test_plus_eight_timezone_is_accepted() -> None:
    end_at = datetime(2026, 10, 8, 20, tzinfo=timezone(timedelta(hours=8)))
    window = TimeWindow(end_at=end_at)

    assert window.end_at == end_at
    assert window.end_at.utcoffset() == timedelta(hours=8)


def test_order_uses_absolute_time_across_offsets() -> None:
    start_at = datetime(2026, 10, 8, 12, tzinfo=timezone(timedelta(hours=8)))
    end_at = datetime(2026, 10, 8, 5, tzinfo=timezone.utc)

    assert TimeWindow(start_at=start_at, end_at=end_at).end_at == end_at


def test_repeated_local_hour_uses_absolute_time() -> None:
    class FoldTimezone(tzinfo):
        def utcoffset(self, value: datetime | None) -> timedelta:
            return timedelta(hours=-5 if value is not None and value.fold else -4)

        def dst(self, value: datetime | None) -> timedelta:
            return timedelta(0)

        def tzname(self, value: datetime | None) -> str:
            return "fold-test"

    local_timezone = FoldTimezone()
    start_at = datetime(2026, 11, 1, 1, 30, tzinfo=local_timezone, fold=1)
    end_at = datetime(2026, 11, 1, 1, 45, tzinfo=local_timezone, fold=0)

    with pytest.raises(ValidationError, match="start_at must be before"):
        TimeWindow(start_at=start_at, end_at=end_at)


def test_model_dump_preserves_unknown_end() -> None:
    start_at = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
    window = TimeWindow(start_at=start_at)

    assert window.model_dump(mode="json") == {
        "start_at": "2026-10-08T12:00:00Z",
        "end_at": None,
    }


def test_model_validate_round_trip() -> None:
    original = TimeWindow(
        start_at=datetime(2026, 10, 8, 12, tzinfo=timezone(timedelta(hours=8))),
        end_at=datetime(2026, 10, 9, 12, tzinfo=timezone(timedelta(hours=8))),
    )

    assert TimeWindow.model_validate(original.model_dump(mode="json")) == original
