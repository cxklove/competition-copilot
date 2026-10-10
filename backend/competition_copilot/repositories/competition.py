"""Read-only competition access independent of storage technology."""

from typing import Literal, Protocol

from competition_copilot.domain.competition import (
    Competition,
    CompetitionEdition,
    CompetitionTrack,
)

RepositoryEntityType = Literal["competition", "edition", "track"]


class RepositoryEntityNotFoundError(LookupError):
    """A requested official Domain entity does not exist."""

    def __init__(self, entity_type: RepositoryEntityType, requested_id: str) -> None:
        self.entity_type = entity_type
        self.requested_id = requested_id
        super().__init__(f"{entity_type} not found: {requested_id}")


class RepositoryDuplicateIdError(ValueError):
    """An adapter found more than one entity with the same ID."""

    def __init__(self, entity_type: RepositoryEntityType, duplicate_id: str) -> None:
        self.entity_type = entity_type
        self.duplicate_id = duplicate_id
        super().__init__(f"duplicate {entity_type} id: {duplicate_id}")


class CompetitionRepository(Protocol):
    """Read verified Domain facts without exposing ingestion artifacts.

    Competitions are ordered by ``id``; editions by ``(year, id)``. Tracks
    retain their reviewed order within an edition. Each entity ID is unique
    across the repository; adapters fail with ``RepositoryDuplicateIdError``
    on duplicates instead of choosing a winner. Returned models are detached
    from repository-held state, so caller mutation cannot update stored data.
    """

    def list_competitions(self) -> list[Competition]:
        """Return all official competitions in ascending ID order."""
        ...

    def get_competition(self, competition_id: str) -> Competition:
        """Return one competition or raise ``RepositoryEntityNotFoundError``."""
        ...

    def list_editions(self) -> list[CompetitionEdition]:
        """Return all editions in ascending ``(year, id)`` order."""
        ...

    def get_edition(self, edition_id: str) -> CompetitionEdition:
        """Return one edition or raise ``RepositoryEntityNotFoundError``."""
        ...

    def list_editions_by_competition(
        self, competition_id: str
    ) -> list[CompetitionEdition]:
        """Return matching editions by ``(year, id)``; unknown IDs yield []."""
        ...

    def list_tracks(self, edition_id: str) -> list[CompetitionTrack]:
        """Return reviewed Track order; zero or unknown editions yield []."""
        ...

    def get_track(self, track_id: str) -> CompetitionTrack:
        """Return one Track or raise ``RepositoryEntityNotFoundError``."""
        ...
