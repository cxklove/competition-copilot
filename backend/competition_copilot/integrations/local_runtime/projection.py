"""Resolve only server-retained public result JSON pointers; no decisions/diffs."""

from competition_copilot.domain.decision import Evidence
from competition_copilot.domain.eligibility import EligibilityDecision
from competition_copilot.domain.plan import CompetitionPlan
from competition_copilot.domain.recommendation_ranking import (
    RecommendationRankingResult,
)
from competition_copilot.domain.replanning import PlanDiff
from competition_copilot.domain.skill_gap import SkillGapDecision
from competition_copilot.domain.source_metadata import SourceMetadata
from competition_copilot.tools.competition import (
    GetCompetitionOutput,
    ListCompetitionsOutput,
)

PUBLIC_MODELS = {model.__name__: model for model in (
    EligibilityDecision, SkillGapDecision, CompetitionPlan, RecommendationRankingResult,
    ListCompetitionsOutput, GetCompetitionOutput,
)}


def presentation(response, receipts):
    entries = []
    if response["outcome"] != "COMPLETED":
        return {"request_id": response["request_id"], "artifacts": []}
    for reference in response["audit"]["results"]:
        for receipt in receipts:
            if receipt.status != "SUCCESS" or receipt.data is None:
                continue
            root = receipt.result_ref.ref_id
            if reference["ref_id"] == root and reference["kind"] == "TOOL_RESULT":
                model = PUBLIC_MODELS.get(type(receipt.data).__name__)
                if model:
                    value = model.model_validate(receipt.data)
                    entries.append({"ref": reference, "model": model.__name__, "value": value.model_dump(mode="json")})
                break
            prefix = root + "#/data"
            if not reference["ref_id"].startswith(prefix + "/"):
                continue
            value = receipt.data.model_dump(mode="json")
            try:
                for part in reference["ref_id"][len(prefix) + 1:].split("/"):
                    key = part.replace("~1", "/").replace("~0", "~")
                    value = value[int(key)] if isinstance(value, list) else value[key]
                model = {"PLAN_DIFF": PlanDiff, "EVIDENCE": Evidence, "SOURCE": SourceMetadata}.get(reference["kind"])
                if model is None:
                    continue
                canonical = model.model_validate(value)
            except (ValueError, TypeError, KeyError, IndexError):
                continue  # A reference may name another artifact type; never invent a body.
            entries.append({"ref": reference, "model": model.__name__, "value": canonical.model_dump(mode="json")})
            break
    return {"request_id": response["request_id"], "artifacts": entries}
