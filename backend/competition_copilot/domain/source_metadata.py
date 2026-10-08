from enum import Enum

from pydantic import AwareDatetime, BaseModel, ConfigDict, HttpUrl


class SourceType(str, Enum):
    OFFICIAL = "official"
    UNIVERSITY = "university"
    ORGANIZER = "organizer"
    MANUAL = "manual"
    OTHER = "other"


class VerificationStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class SourceMetadata(BaseModel):
    """Immutable provenance and verification state for a competition fact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_url: HttpUrl
    source_type: SourceType
    observed_at: AwareDatetime
    verification_status: VerificationStatus
