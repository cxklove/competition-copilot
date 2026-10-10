"""Executable error contracts shared by future repository adapters."""

import pytest

from competition_copilot.repositories import (
    RepositoryDuplicateIdError,
    RepositoryEntityNotFoundError,
)


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
