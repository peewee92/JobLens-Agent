"""Six frozen contract examples, NOT live Agent-vs-workflow effectiveness evidence."""
from dataclasses import asdict
import json
from pathlib import Path
from app.agent.intent import CareerIntentRouter
from app.agent.tool_registry import CareerAgentToolRegistry
from app.agent.tool_selection import CareerAgentToolSelector
from app.evals.career_tool_selection import (
    ToolSelectionEvalAdapter, ToolSelectionEvalReplayModel,
    load_career_tool_selection_eval_dataset, evaluate_career_tool_selections,
)


def report():
    path = Path(__file__).resolve().parents[3] / 'data/evals/career-tool-selection/career-tool-selection-v1.jsonl'
    all_cases = load_career_tool_selection_eval_dataset(path)
    # One case per existing category; do not claim the full release gate passed.
    chosen = {}
    for case in all_cases:
        chosen.setdefault(case.category, case)
    cases = tuple(chosen.values())
    class ForbiddenWorkflow:
        def execute(self, *args, **kwargs):
            raise AssertionError('Contract evidence must not execute business workflows')
    registry = CareerAgentToolRegistry(ranking=ForbiddenWorkflow(), target_cohort_gaps=ForbiddenWorkflow(), job_preparation=ForbiddenWorkflow())
    adapter = ToolSelectionEvalAdapter(router=CareerIntentRouter(model=ToolSelectionEvalReplayModel.from_cases(cases)),
                                      selector=CareerAgentToolSelector(registry=registry), registry=registry)
    evaluation = evaluate_career_tool_selections(adapter=adapter, cases=cases, require_release_dataset=False)
    return {'kind': 'frozen-contract-replay', 'liveModelQualityVerified': False,
            'agentBenefitOverWorkflowVerified': False, 'releaseGateClaimed': False,
            'evaluation': asdict(evaluation),
            'examples': [{'caseId': c.case_id, 'message': c.message, 'expectedOutcome': c.expected.outcome.value,
                          'execution': asdict(adapter.run(case=c))} for c in cases]}


if __name__ == '__main__':
    result = report()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['evaluation']['failed_cases'] == 0 else 1)
