import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from competition_copilot.domain.resource import LearningResource, ResourceType
from competition_copilot.domain.source_metadata import (
    SourceMetadata,
    SourceType,
    VerificationStatus,
)

MINIMAL_RESOURCE = {
    "id": "resource-1",
    "title": "Python Guide",
    "resource_type": ResourceType.DOCUMENTATION,
    "url": "https://example.com/python",
}


def test_valid_minimal_resource() -> None:
    resource = LearningResource(**MINIMAL_RESOURCE)

    assert resource.id == "resource-1"
    assert resource.title == "Python Guide"
    assert resource.resource_type is ResourceType.DOCUMENTATION
    assert str(resource.url) == "https://example.com/python"
    assert resource.description is None
    assert resource.skill_ids == []
    assert resource.source is None


def test_valid_complete_resource() -> None:
    source = SourceMetadata(
        source_url="https://example.com/catalog",
        source_type=SourceType.OFFICIAL,
        observed_at=datetime(2026, 10, 8, tzinfo=timezone.utc),
        verification_status=VerificationStatus.VERIFIED,
    )
    resource = LearningResource(
        id="  resource-1  ",
        title="  Python Guide  ",
        resource_type=ResourceType.COURSE,
        url="http://example.com/python",
        description="  Learn Python fundamentals.  ",
        skill_ids=[" python ", "algorithms"],
        source=source,
    )

    assert resource.id == "resource-1"
    assert resource.title == "Python Guide"
    assert resource.resource_type is ResourceType.COURSE
    assert str(resource.url) == "http://example.com/python"
    assert resource.description == "Learn Python fundamentals."
    assert resource.skill_ids == ["python", "algorithms"]
    assert resource.source is source


@pytest.mark.parametrize("identifier", ["", " \t\n "])
def test_empty_id_is_rejected(identifier: str) -> None:
    with pytest.raises(ValidationError, match="id"):
        LearningResource(**{**MINIMAL_RESOURCE, "id": identifier})


@pytest.mark.parametrize("title", ["", " \t\n "])
def test_empty_title_is_rejected(title: str) -> None:
    with pytest.raises(ValidationError, match="title"):
        LearningResource(**{**MINIMAL_RESOURCE, "title": title})


@pytest.mark.parametrize("url", ["not a URL", "ftp://example.com/resource"])
def test_invalid_or_non_http_url_is_rejected(url: str) -> None:
    with pytest.raises(ValidationError, match="url"):
        LearningResource(**{**MINIMAL_RESOURCE, "url": url})


@pytest.mark.parametrize("url", ["http://example.com", "https://example.com"])
def test_http_and_https_urls_are_accepted(url: str) -> None:
    resource = LearningResource(**{**MINIMAL_RESOURCE, "url": url})

    assert str(resource.url) == f"{url}/"


@pytest.mark.parametrize("resource_type", list(ResourceType))
def test_all_resource_types_are_accepted(resource_type: ResourceType) -> None:
    resource = LearningResource(**{**MINIMAL_RESOURCE, "resource_type": resource_type})

    assert resource.resource_type is resource_type


def test_unknown_resource_type_is_rejected() -> None:
    with pytest.raises(ValidationError, match="resource_type"):
        LearningResource(**{**MINIMAL_RESOURCE, "resource_type": "podcast"})


def test_description_is_optional_and_trimmed() -> None:
    assert LearningResource(**MINIMAL_RESOURCE).description is None
    resource = LearningResource(**{**MINIMAL_RESOURCE, "description": "  Guide.  "})

    assert resource.description == "Guide."


@pytest.mark.parametrize("description", ["", " \t\n "])
def test_blank_description_is_rejected(description: str) -> None:
    with pytest.raises(ValidationError, match="description"):
        LearningResource(**{**MINIMAL_RESOURCE, "description": description})


def test_empty_skill_ids_are_allowed() -> None:
    resource = LearningResource(**{**MINIMAL_RESOURCE, "skill_ids": []})

    assert resource.skill_ids == []


def test_skill_ids_are_trimmed_deduplicated_and_ordered() -> None:
    resource = LearningResource(
        **{
            **MINIMAL_RESOURCE,
            "skill_ids": [" python ", "RAG", "python", "rag", "RAG"],
        }
    )

    assert resource.skill_ids == ["python", "RAG", "rag"]


@pytest.mark.parametrize("skill_id", ["", " \t\n "])
def test_blank_skill_id_is_rejected(skill_id: str) -> None:
    with pytest.raises(ValidationError, match="skill_ids"):
        LearningResource(**{**MINIMAL_RESOURCE, "skill_ids": ["python", skill_id]})


def test_skill_ids_do_not_require_repository_lookup() -> None:
    resource = LearningResource(
        **{**MINIMAL_RESOURCE, "skill_ids": ["not-yet-stored"]}
    )

    assert resource.skill_ids == ["not-yet-stored"]


def test_source_metadata_is_accepted() -> None:
    source = SourceMetadata(
        source_url="https://example.com/catalog",
        source_type=SourceType.UNIVERSITY,
        observed_at=datetime(2026, 10, 8, tzinfo=timezone.utc),
        verification_status=VerificationStatus.PENDING,
    )
    resource = LearningResource(**{**MINIMAL_RESOURCE, "source": source})

    assert resource.source is source


def test_serialization() -> None:
    resource = LearningResource(
        **{
            **MINIMAL_RESOURCE,
            "description": "  Official guide.  ",
            "skill_ids": [" python ", "python"],
        }
    )
    expected = {
        "id": "resource-1",
        "title": "Python Guide",
        "resource_type": "documentation",
        "url": "https://example.com/python",
        "description": "Official guide.",
        "skill_ids": ["python"],
        "source": None,
    }

    assert resource.model_dump(mode="json") == expected
    assert json.loads(resource.model_dump_json()) == expected


def test_model_validate_round_trip() -> None:
    original = LearningResource(
        **{
            **MINIMAL_RESOURCE,
            "skill_ids": ["python", "algorithms"],
            "source": SourceMetadata(
                source_url="https://example.com/catalog",
                source_type=SourceType.OFFICIAL,
                observed_at=datetime(2026, 10, 8, tzinfo=timezone.utc),
                verification_status=VerificationStatus.VERIFIED,
            ),
        }
    )

    restored = LearningResource.model_validate(original.model_dump(mode="json"))

    assert restored == original
    assert restored.resource_type is ResourceType.DOCUMENTATION
    assert isinstance(restored.source, SourceMetadata)
