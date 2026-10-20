"""Offline controlled local revision proposal, never an official event/approval.

Reuses existing P8/P11 test constructors, real seed identities and unchanged
validators. The browser never receives this internal prepared input/authority.
P12.5 replaces the proposal's synthetic provenance only after explicit approval.
"""

import argparse
import json
import runpy
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def fixture():
    values = runpy.run_path(str(ROOT / "backend/tests/integration/test_real_adaptive_replanning.py"))
    environment = values["real_context"].__wrapped__.__globals__
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    environment["T0"] = start
    for index, key in enumerate(("OBSERVED", "EVALUATED", "DECIDED", "APPROVED", "EXECUTED"), 1):
        environment[key] = start + timedelta(days=index)
    context = values["real_context"].__wrapped__()
    impact = values["impact_for"](context, "replan")
    decision = values["ReplanningDecisionService"]().decide((impact,), context[0], evaluated_at=environment["DECIDED"])
    proposal = values["authorized_cancellation"](context[0], decision)
    return json.dumps({"notice": "SYNTHETIC LOCAL DEMO: not an official change or real human approval",
                       "student": context[1].model_dump(mode="json"),
                       "proposal": proposal.model_dump(mode="json")}, ensure_ascii=False, indent=2) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = ROOT / "data/local_runtime/controlled_revision.json"
    value = fixture()
    from competition_copilot.domain.replanning import PlanReference
    from competition_copilot.domain.replanning_input import ReplanningInput
    source = ReplanningInput.model_validate(json.loads(value)["proposal"])
    public = json.dumps(PlanReference.from_plan(source.before).model_dump(mode="json"), indent=2) + "\n"
    for target, content in ((path, value), (ROOT / "frontend/src/demo/local-plan.json", public)):
        if args.check:
            if target.read_text(encoding="utf-8") != content:
                raise SystemExit("Local controlled fixture drift")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
