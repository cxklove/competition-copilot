"""Executable error contracts shared by future repository adapters."""

import pytest

from competition_copilot.domain.competition import (
    Competition,
    CompetitionEdition,
    CompetitionTrack,
)
from competition_copilot.repositories import (
    CompetitionRepository,
    RepositoryDuplicateIdError,
    RepositoryEntityNotFoundError,
)


class _CompetitionWithoutEditions(CompetitionRepository):
    """Represent a valid abstract state that a Seed cannot encode alone."""

    def __init__(self) -> None:
        self.competition = Competition(id="solo", name="Solo")

    def list_competitions(self) -> list[Competition]:
        return [self.competition.model_copy(deep=True)]

    def get_competition(self, competition_id: str) -> Competition:
        if competition_id != self.competition.id:
            raise RepositoryEntityNotFoundError("competition", competition_id)
        return self.competition.model_copy(deep=True)

    def list_editions(self) -> list[CompetitionEdition]:
        return []

    def get_edition(self, edition_id: str) -> CompetitionEdition:
        raise RepositoryEntityNotFoundError("edition", edition_id)

    def list_editions_by_competition(
        self, competition_id: str
    ) -> list[CompetitionEdition]:
        self.get_competition(competition_id)
        return []

    def list_tracks(self, edition_id: str) -> list[CompetitionTrack]:
        raise RepositoryEntityNotFoundError("edition", edition_id)

    def get_track(self, track_id: str) -> CompetitionTrack:
        raise RepositoryEntityNotFoundError("track", track_id)


def test_existing_competition_without_editions_differs_from_unknown_parent() -> None:
    repository: CompetitionRepository = _CompetitionWithoutEditions()

    assert repository.list_editions_by_competition("solo") == []
    with pytest.raises(RepositoryEntityNotFoundError) as raised:
        repository.list_editions_by_competition("unknown")
    assert raised.value.entity_type == "competition"
    assert raised.value.requested_id == "unknown"


@pytest.mark.parametrize("entity_type", ["competition", "edition", "track"])
def test_not_found_error_identifies_entity_and_requested_id(
    entity_type: str,
) -> None:
    error = RepositoryEntityNotFoundError(entity_type, "missing-id")

    assert isinstance(error, LookupError)
    assert error.entity_type == entity_type
    assert error.requested_id == "missing-id"
    assert str(error) == f"{entity_type} not found: missing-id"


@pytest.mark.parametrize("entity_type", ["competition", "edition", "track"])
def test_duplicate_error_identifies_entity_and_conflicting_id(
    entity_type: str,
) -> None:
    error = RepositoryDuplicateIdError(entity_type, "repeated-id")

    assert isinstance(error, ValueError)
    assert error.entity_type == entity_type
    assert error.duplicate_id == "repeated-id"
    assert str(error) == f"duplicate {entity_type} id: repeated-id"
