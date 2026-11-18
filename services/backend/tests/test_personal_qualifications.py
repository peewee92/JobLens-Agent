import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest

from app.application.job_requirements.models import (
    JobRequirementExtractionOutput, ProposedJobRequirement,
)
from app.application.job_requirements.personal_qualifications import preserve_grounded_qualifications
from app.application.job_requirements.validation import MAX_REQUIREMENTS_PER_RUN
from app.domain.job_requirements import RequirementImportance as I, RequirementType as T
from app.llm.job_requirement_extractors import OpenAIJobRequirementExtractor
from app.workflows.job_requirement_extraction import (
    EXTRACTOR_VERSION, PERSONAL_EXTRACTOR_VERSION, ExtractJobRequirementsWorkflow,
)

HOLDOUT = Path(__file__).resolve().parents[3] / "data/evals/requirement-extraction/public-source-holdout-v1.jsonl"
CASES = {row["caseId"]: row["description"] for row in map(json.loads, HOLDOUT.read_text().splitlines())}
RESIDENCY = "Candidates must live in the United States"
AUTH = "hold US work authorization"
COMPOUND = f"{RESIDENCY} and {AUTH}."
DEGREE_EN = "A relevant bachelor's degree may be substituted with comparable hands-on experience."
DEGREE_ZH = "相关工程专业本科学历或等效实践"


def candidate(text, type_, importance, source_id):
    return dict(originalText=text, type=type_.value, importance=importance.value,
                sourceCandidateId=source_id, normalizedCapability=None, confidence=.95)


@pytest.mark.parametrize(("case", "rows", "expected"), [
    ("public-cloud-data", [candidate(COMPOUND, T.CONSTRAINT, I.MUST_HAVE, "S0001"),
                           candidate(DEGREE_EN, T.EDUCATION, I.PREFERRED, "S0002")],
     [RESIDENCY, AUTH, DEGREE_EN]),
    ("public-rf-test", [candidate(DEGREE_ZH, T.EDUCATION, I.MUST_HAVE, "S0002")], [DEGREE_ZH]),
])
def test_real_output_shape_preserves_distinct_gates_in_local_workflow_only(case, rows, expected):
    uow = Mock()

    @contextmanager
    def traces():
        yield uow

    # Minimal reproduced rows from the live response, replayed through the real adapter, with no network.
    def replay(_):
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"requirements": rows})}}]})

    with httpx.Client(transport=httpx.MockTransport(replay)) as client:
        adapter = OpenAIJobRequirementExtractor(api_key="not-live", model="qwen3.8-flash",
            api_style="chat_completions", client=client)
        frozen = ExtractJobRequirementsWorkflow(adapter, traces).execute(job_id="frozen", description=CASES[case])
        local = ExtractJobRequirementsWorkflow(adapter, traces, personal_skill_proof=True).execute(
            job_id="local", description=CASES[case])
    assert frozen.extractor_version == EXTRACTOR_VERSION
    assert any(row.type is T.EDUCATION for row in frozen.requirements)
    assert local.extractor_version == PERSONAL_EXTRACTOR_VERSION
    assert len(PERSONAL_EXTRACTOR_VERSION) <= 100
    fixed = [row for row in local.requirements if row.original_text in expected]
    assert [row.original_text for row in fixed] == expected
    assert all(row.type is T.CONSTRAINT and row.importance is I.MUST_HAVE for row in fixed)
    assert all(row.original_text in row.evidence_span in CASES[case] for row in fixed)
    assert all(row.normalized_capability is None for row in fixed)
    assert {item["strategy"] for item in uow.traces.add.call_args.args[0].output["personalQualificationRepairs"]} == (
        {"preserve_degree_or_practice", "separate_residency_and_work_authorization"}
        if case == "public-cloud-data" else {"preserve_degree_or_practice"}
    )


@pytest.mark.parametrize(("description", "quote", "evidence", "type_", "importance"), [
    ("Preferred: " + DEGREE_EN, DEGREE_EN, "Preferred: " + DEGREE_EN, T.EDUCATION, I.PREFERRED),
    ("Required: strong SQL; Preferred: " + DEGREE_EN, DEGREE_EN, "Required: strong SQL; Preferred: " + DEGREE_EN, T.EDUCATION, I.PREFERRED),
    ("要求：优先接受" + DEGREE_ZH, "优先接受" + DEGREE_ZH, "要求：优先接受" + DEGREE_ZH, T.EDUCATION, I.PREFERRED),
    ("有意向请联系我们。 " + DEGREE_EN, DEGREE_EN, DEGREE_EN, T.EDUCATION, I.PREFERRED),
    ("Required: " + DEGREE_EN, DEGREE_EN, "Preferred: " + DEGREE_EN, T.EDUCATION, I.PREFERRED),
    (f"Applicants must live in X or Y and {AUTH}.", f"Applicants must live in X or Y and {AUTH}.",
     f"Applicants must live in X or Y and {AUTH}.", T.CONSTRAINT, I.MUST_HAVE),
    ("We do not sponsor work visas.", "We do not sponsor work visas.", "We do not sponsor work visas.", T.CONSTRAINT, I.MUST_HAVE),
])
def test_does_not_turn_optional_unbound_or_ambiguous_text_into_new_gates(description, quote, evidence, type_, importance):
    raw = JobRequirementExtractionOutput((ProposedJobRequirement(type_, quote, None, importance, evidence, .9),))
    assert preserve_grounded_qualifications(description, raw) == (raw, ())


def test_does_not_break_valid_compound_when_result_is_at_max_size():
    raw = JobRequirementExtractionOutput((ProposedJobRequirement(T.CONSTRAINT, COMPOUND, None, I.MUST_HAVE, COMPOUND, .9),)
        * MAX_REQUIREMENTS_PER_RUN)
    assert preserve_grounded_qualifications(COMPOUND, raw) == (raw, ())


@pytest.mark.parametrize(("quote", "reason_fragment"), [
    (DEGREE_EN, "等效实践"),
    (DEGREE_ZH, "等效实践"),
    (RESIDENCY, "居住地"),
    (AUTH, "工作授权"),
    (COMPOUND, "分别核实"),
])
def test_whole_clause_mentions_do_not_prove_personal_qualifications(quote, reason_fragment):
    from dataclasses import replace
    from .test_eligibility_alternative_group import _only_result, _profile, _requirement
    from app.application.eligibility.models import RequirementFitStatus

    requirement = replace(_requirement(0, quote), extractor_version=PERSONAL_EXTRACTOR_VERSION)
    outcome = _only_result(_profile(f"Previous role mentioned ({quote}); it does not establish eligibility."), requirement)
    assert outcome.status is RequirementFitStatus.CONDITIONAL
    assert not outcome.evidence_ids
    assert reason_fragment in outcome.reason


def test_personal_job_duty_remains_available_for_fit_but_does_not_block_eligibility():
    from dataclasses import replace
    from .test_eligibility_alternative_group import _extraction, _profile, _requirement
    from app.application.eligibility.evaluator import evaluate_eligibility
    from app.application.eligibility.models import EligibilityDecision, RequirementFitStatus

    duty = _requirement(0, "Build transformations", requirement_type=T.RESPONSIBILITY)
    profile = _profile("Experience with data visualizations.")
    frozen = evaluate_eligibility(profile=profile, extraction=_extraction(duty))
    local = replace(_extraction(replace(duty, extractor_version=PERSONAL_EXTRACTOR_VERSION)),
                    extractor_version=PERSONAL_EXTRACTOR_VERSION)
    result = evaluate_eligibility(profile=profile, extraction=local)
    assert frozen.eligibility is EligibilityDecision.CONDITIONAL
    assert result.eligibility is EligibilityDecision.ELIGIBLE
    assert result.requirements[0].status is RequirementFitStatus.CONDITIONAL
    assert result.requirements[0].type is T.RESPONSIBILITY
    with_hard_requirement = replace(local, requirements=(*local.requirements, _requirement(1, RESIDENCY)),
                                   requirement_count=2)
    assert evaluate_eligibility(profile=profile, extraction=with_hard_requirement).eligibility is EligibilityDecision.CONDITIONAL
