"""Deterministic timezone evidence checks; all new time facts are synthetic."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from competition_copilot.ingestion.models import RawCompetitionData
from competition_copilot.ingestion.normalizer import (
    CompetitionNormalizer,
    NormalizationError,
)
from competition_copilot.ingestion.seed import CompetitionSeedEnvelope


def raw_values(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "competition_id": "example",
        "name": "示例赛事",
        "edition_id": "example-2026",
        "edition_name": "2026 示例赛事",
        "edition_year": 2026,
        "source_url": "https://example.cn/notice",
        "source_type": "official",
        "observed_at": "2026-10-09T12:00:00+08:00",
    }
    data.update(overrides)
    return data


def provenance(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "field": "registration_end",
        "timezone_name": "Asia/Shanghai",
        "timezone_basis": "jurisdiction_default",
        "precision": "minute",
        "source_text": "报名截止：2026年3月31日16:00",
    }
    data.update(overrides)
    return data


def test_old_raw_loads_without_temporal_provenance() -> None:
    raw = RawCompetitionData.model_validate(raw_values())

    assert raw.temporal_provenance == []


@pytest.mark.parametrize("basis", ["source_explicit", "jurisdiction_default"])
def test_valid_timezone_basis_and_matching_shanghai_offset(basis: str) -> None:
    source_text = (
        "报名截止：2026年3月31日16:00（UTC+8）"
        if basis == "source_explicit"
        else "报名截止：2026年3月31日16:00"
    )
    raw = RawCompetitionData.model_validate(
        raw_values(
            registration_end="2026-03-31T16:00:00+08:00",
            temporal_provenance=[
                provenance(timezone_basis=basis, source_text=source_text)
            ],
        )
    )

    assert raw.temporal_provenance[0].timezone_basis == basis
    _, edition, _ = CompetitionNormalizer().normalize(raw)
    assert edition.registration_window.start_at is None
    assert edition.registration_window.end_at.isoformat() == (
        "2026-03-31T16:00:00+08:00"
    )


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"timezone_name": "Not/A_Zone"}, "timezone_name"),
        ({"timezone_name": ""}, "timezone_name"),
        ({"timezone_basis": "inferred_from_url"}, "timezone_basis"),
        ({"source_text": "  "}, "source_text"),
    ],
)
def test_invalid_temporal_evidence_is_rejected(
    overrides: dict[str, object], error: str
) -> None:
    with pytest.raises(ValidationError, match=error):
        RawCompetitionData.model_validate(
            raw_values(
                registration_end="2026-03-31T16:00:00+08:00",
                temporal_provenance=[provenance(**overrides)],
            )
        )


def test_duplicate_temporal_field_is_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate temporal provenance field"):
        RawCompetitionData.model_validate(
            raw_values(
                registration_end="2026-03-31T16:00:00+08:00",
                temporal_provenance=[provenance(), provenance()],
            )
        )


def test_provenance_cannot_point_to_null_time() -> None:
    with pytest.raises(ValidationError, match="requires a time value"):
        RawCompetitionData.model_validate(
            raw_values(temporal_provenance=[provenance()])
        )


def test_shanghai_plus_nine_offset_is_rejected() -> None:
    with pytest.raises(ValidationError, match="inconsistent with Asia/Shanghai"):
        RawCompetitionData.model_validate(
            raw_values(
                registration_end="2026-03-31T16:00:00+09:00",
                temporal_provenance=[provenance()],
            )
        )


@pytest.mark.parametrize("value", ["2026-03-31", "2026-03-31T16:00:00"])
def test_normalizer_still_rejects_date_only_and_naive_time(value: str) -> None:
    raw = RawCompetitionData.model_validate(raw_values(registration_end=value))

    with pytest.raises(NormalizationError, match="timezone-aware ISO datetime"):
        CompetitionNormalizer().normalize(raw)


def test_chinese_text_and_cn_url_do_not_infer_timezone() -> None:
    raw = RawCompetitionData.model_validate(
        raw_values(registration_end="2026-03-31T16:00:00")
    )

    assert raw.temporal_provenance == []
    with pytest.raises(NormalizationError):
        CompetitionNormalizer().normalize(raw)


def test_existing_four_seed_1_0_artifacts_still_load() -> None:
    root = Path(__file__).resolve().parents[3]
    names = (
        "huawei-ict-2026.json",
        "c4-big-data-challenge-2026.json",
        "nuedc-analog-system-2026.json",
        "gcxl-engineering-practice-innovation-2027.json",
    )

    for name in names:
        path = root / "data/seed" / name
        assert path.is_file(), f"Missing historical Seed: {path}"
        seed = CompetitionSeedEnvelope.model_validate_json(path.read_bytes())
        assert seed.schema_version == "1.0"
        assert seed.temporal_provenance == []


def test_batch_01_five_seed_1_1_artifacts_load() -> None:
    root = Path(__file__).resolve().parents[3]
    names = (
        "4c-computer-design-2026.json",
        "china-intl-college-students-innovation-2026.json",
        "fwwb-2026.json",
        "meicc-2026.json",
        "robomaster-rmuc-2026.json",
    )

    for name in names:
        path = root / "data/seed" / name
        assert path.is_file(), f"Missing Batch 01 Seed: {path}"
        seed = CompetitionSeedEnvelope.model_validate_json(path.read_bytes())
        assert seed.schema_version == "1.1"
