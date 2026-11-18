from dataclasses import replace
import pytest
from app.application.job_requirements.models import JobRequirementExtractionOutput, ProposedJobRequirement
from app.application.job_requirements.personal_skill_proof import preserve_skill_requiring_proof
from app.domain.job_requirements import RequirementImportance as I, RequirementType as T


def item(text, *, kind=T.CONSTRAINT, importance=I.MUST_HAVE):
    return ProposedJobRequirement(type=kind, importance=importance, original_text=text,
        evidence_span=text, normalized_capability=None, confidence=.9)


@pytest.mark.parametrize(("text", "capability"), [
    ("熟练掌握 Python，能够以实际项目说明服务开发经验", "Python"),
    ("熟悉 Agent 应用开发，能够说明工具调用和失败处理", "Agent 应用开发"),
    ("掌握 SQL，能说明查询优化过程。", "SQL"),
    ("任职要求：熟练掌握 Python，能够以实际项目说明服务开发经验。", "Python"),
    ("任职要求：熟悉 Agent 应用开发，能够说明工具调用和失败处理。", "Agent 应用开发"),
])
def test_exact_skill_with_proof_keeps_its_fact_and_becomes_comparable(text, capability):
    original = item(text)
    output, repairs = preserve_skill_requiring_proof("任职要求：\n" + text, JobRequirementExtractionOutput((original,)))
    assert output.requirements == (replace(original, type=T.SKILL, normalized_capability=capability),)
    assert repairs == (0,)


@pytest.mark.parametrize("text", [
    "熟悉 Python 或 Go，能够说明服务开发经验",
    "熟悉 Python 和 SQL，能够说明数据处理经验",
    "熟悉五年以上从业经验，能够说明项目经验",
    "熟悉 Python，能够说明服务开发经验者优先",
    "熟悉 Python，能够说明服务开发经验以及故障处理；熟悉 SQL",
    "至少5年以上工作经验，能够以实际从业记录说明",
    "能用 Python 或 Go 开发服务",
])
def test_alternative_threshold_and_compound_are_never_reinterpreted_as_single_skill(text):
    output = JobRequirementExtractionOutput((item(text),))
    assert preserve_skill_requiring_proof("任职要求：\n" + text, output) == (output, ())


def test_duty_bonus_ungrounded_and_existing_skill_are_not_promoted():
    text = "熟悉 Python，能够说明服务开发经验"
    for description, original in [
        ("工作职责：\n"+text, item(text)),
        ("任职要求：\n"+text, item(text, importance=I.BONUS)),
        ("任职要求：\n另一个描述", item(text)),
    ]:
        output = JobRequirementExtractionOutput((original,))
        assert preserve_skill_requiring_proof(description, output) == (output, ())


def test_personal_workflow_versions_the_repair_and_retains_the_original_trace():
    from contextlib import contextmanager
    from unittest.mock import Mock
    from app.application.job_requirements.models import JobRequirementExtractorResult
    from app.workflows.job_requirement_extraction import ExtractJobRequirementsWorkflow, PERSONAL_EXTRACTOR_VERSION
    text = "熟练掌握 Python，能够以实际项目说明服务开发经验与故障处理过程。"
    description = "任职要求：\n" + text + "\n我们希望你如实说明以上要求的相关经历。"
    extractor = Mock(model_name="synthetic-provider", max_provider_calls_per_execution=1)
    extractor.extract.return_value = JobRequirementExtractorResult(
        JobRequirementExtractionOutput((item(text),)), "synthetic-provider", 100, 50, 1)
    uow = Mock()
    @contextmanager
    def traces():
        yield uow
    proposal = ExtractJobRequirementsWorkflow(extractor, traces, personal_skill_proof=True).execute(job_id="test-job", description=description)
    assert proposal.extractor_version == PERSONAL_EXTRACTOR_VERSION
    assert proposal.requirements[0].normalized_capability == "Python"
    record = uow.traces.add.call_args.args[0]
    assert record.version == PERSONAL_EXTRACTOR_VERSION
    assert record.output["personalSkillProofRepairs"] == [0]
    assert record.input_refs["providerCalls"] == 1
    assert proposal.requirements[0].original_text == text
