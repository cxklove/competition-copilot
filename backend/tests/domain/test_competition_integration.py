import ast
import inspect
import json
from datetime import datetime, timedelta, timezone
from types import ModuleType

import pytest

from competition_copilot.domain import competition, source_metadata, temporal
from competition_copilot.domain.competition import (
    Competition,
    CompetitionEdition,
    CompetitionTrack,
)
from competition_copilot.domain.source_metadata import (
    SourceMetadata,
    SourceType,
    VerificationStatus,
)
from competition_copilot.domain.temporal import TimeWindow


@pytest.fixture
def local_competition_chain() -> tuple[Competition, CompetitionEdition, CompetitionTrack]:
    """Synthetic, unverified data for domain integration tests only."""
    competition_model = Competition(id="huawei-ict", name="Fixture ICT Competition")
    source = SourceMetadata(
        source_url="https://example.invalid/fixture",
        source_type=SourceType.MANUAL,
        observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        verification_status=VerificationStatus.PENDING,
    )
    registration_window = TimeWindow(
        start_at=datetime(2026, 1, 2, tzinfo=timezone(timedelta(hours=8))),
        end_at=datetime(2026, 2, 2, tzinfo=timezone(timedelta(hours=8))),
    )
    edition = CompetitionEdition(
        id="huawei-ict-2026",
        competition_id=competition_model.id,
        year=2026,
        name="Fixture 2026 Season",
        registration_window=registration_window,
        source=source,
    )
    track = CompetitionTrack(
        id="huawei-ict-2026-innovation",
        edition_id=edition.id,
        name="Fixture Innovation Track",
        source=source,
    )
    return competition_model, edition, track


def test_competition_can_be_created_independently() -> None:
    competition_model = Competition(id="huawei-ict", name="Fixture ICT Competition")

    assert competition_model.id == "huawei-ict"
    assert competition_model.name == "Fixture ICT Competition"


def test_local_competition_chain_uses_ids_and_value_objects(
    local_competition_chain: tuple[Competition, CompetitionEdition, CompetitionTrack],
) -> None:
    competition_model, edition, track = local_competition_chain

    assert edition.competition_id == competition_model.id
    assert track.edition_id == edition.id
    assert isinstance(edition.registration_window, TimeWindow)
    assert isinstance(edition.source, SourceMetadata)
    assert isinstance(track.source, SourceMetadata)
    assert edition.source.verification_status is VerificationStatus.PENDING


def test_local_chain_serializes_and_round_trips(
    local_competition_chain: tuple[Competition, CompetitionEdition, CompetitionTrack],
) -> None:
    competition_model, edition, track = local_competition_chain
    payloads = [model.model_dump(mode="json") for model in local_competition_chain]

    json.dumps(payloads)
    assert payloads[1]["registration_window"]["start_at"].endswith("+08:00")
    assert payloads[1]["source"]["verification_status"] == "pending"
    assert payloads[1]["competition_id"] == payloads[0]["id"]
    assert payloads[2]["edition_id"] == payloads[1]["id"]
    assert Competition.model_validate(payloads[0]) == competition_model
    assert CompetitionEdition.model_validate(payloads[1]) == edition
    assert CompetitionTrack.model_validate(payloads[2]) == track


def test_foreign_keys_are_not_checked_against_a_database() -> None:
    edition = CompetitionEdition(
        id="fixture-edition",
        competition_id="competition-not-stored",
        year=2026,
        name="Fixture Edition",
    )
    track = CompetitionTrack(
        id="fixture-track",
        edition_id="edition-not-stored",
        name="Fixture Track",
    )

    assert edition.competition_id == "competition-not-stored"
    assert track.edition_id == "edition-not-stored"


@pytest.mark.parametrize("module", [competition, source_metadata, temporal])
def test_domain_models_have_no_external_layer_imports(module: ModuleType) -> None:
    allowed_imports = {
        "competition_copilot.domain.source_metadata",
        "competition_copilot.domain.temporal",
        "datetime",
        "enum",
        "pydantic",
        "typing",
    }
    tree = ast.parse(inspect.getsource(module))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name in allowed_imports for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module in allowed_imports
