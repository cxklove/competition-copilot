"""Abstract data-access contracts for verified competition facts."""

from competition_copilot.repositories.competition import (
    CompetitionRepository,
    RepositoryDuplicateIdError,
    RepositoryEntityNotFoundError,
)

__all__ = [
    "CompetitionRepository",
    "RepositoryDuplicateIdError",
    "RepositoryEntityNotFoundError",
]
