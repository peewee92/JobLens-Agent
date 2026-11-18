import json
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.application.job_requirements.models import (
    JobRequirementExtractionOutput,
    JobRequirementExtractorResult,
    ProposedJobRequirement,
)
from app.application.job_requirements.personal_optional_skill import preserve_explicit_optional_skill
from app.domain.job_requirements import RequirementImportance as I, RequirementType as T
from app.workflows.job_requirement_extraction import (
    EXTRACTOR_VERSION, PERSONAL_EXTRACTOR_VERSION, ExtractJobRequirementsWorkflow,
)

HOLDOUT = Path(__file__).resolve().parents[3] / "data/evals/requirement-extraction/public-source-holdout-v1.jsonl"
FIRMWARE = next(row["description"] for row in map(json.loads, HOLDOUT.read_text().splitlines())
                if row["caseId"] == "public-embedded-firmware")
FULL_LINE = "competence in embedded C/C++ on ARM Cortex-M, using bare-metal and RTOS environments (FreeRTOS is advantageous, not mandatory)."
EXPLICIT = "FreeRTOS is advantageous, not mandatory"


def skill(capability, text, span):
    return ProposedJobRequirement(T.SKILL, text, capability, I.MUST_HAVE, span, .9)


@pytest.mark.parametrize("original", [EXPLICIT, "FreeRTOS"])
def test_public_posting_downgrades_only_explicit_optional_skill_in_local_workflow(original):
    firmware = skill("C/C++", "competence in embedded C/C++ on ARM Cortex-M", FULL_LINE)
    freertos = skill("FreeRTOS", original, FULL_LINE)
    extractor = Mock(model_name="fixture-provider")
    extractor.extract.return_value = JobRequirementExtractorResult(
        JobRequirementExtractionOutput((firmware, freertos)), "fixture-provider", 100, 50, 1)
    uow = Mock()

    @contextmanager
    def traces():
        yield uow

    frozen = ExtractJobRequirementsWorkflow(extractor, traces).execute(job_id="test-job", description=FIRMWARE)
    local = ExtractJobRequirementsWorkflow(extractor, traces, personal_skill_proof=True).execute(
        job_id="test-job", description=FIRMWARE)
    assert frozen.extractor_version == EXTRACTOR_VERSION
    assert frozen.requirements == (firmware, freertos)
    assert local.extractor_version == PERSONAL_EXTRACTOR_VERSION
    assert local.requirements == (firmware, replace(freertos, importance=I.PREFERRED))
    trace = uow.traces.add.call_args.args[0]
    assert trace.output["personalOptionalSkillRepairs"] == [1]
    assert trace.input_refs["providerCalls"] == 1


@pytest.mark.parametrize(("description", "candidate"), [
    (FIRMWARE, skill("FreeRTOS", FULL_LINE, FULL_LINE)),
    (FIRMWARE, skill("C/C++", EXPLICIT, FULL_LINE)),
    (FIRMWARE, skill("FreeRTOS", EXPLICIT, "help diagnose device failures")),
    (FIRMWARE, skill("FreeRTOS", EXPLICIT, "FreeRTOS is optional but not in the source")),
    (FIRMWARE, skill("FreeRTOS", EXPLICIT, FULL_LINE + " " + FULL_LINE)),
    ("FreeRTOS required. " + FULL_LINE, skill("FreeRTOS", "FreeRTOS", "FreeRTOS required")),
    ("FreeRTOS is helpful for monitoring. FreeRTOS is required for diagnostics.",
     skill("FreeRTOS", "FreeRTOS", "FreeRTOS is helpful for monitoring")),
    ("FreeRTOS is helpful but not required for prototyping.",
     skill("FreeRTOS", "FreeRTOS is helpful but not required for prototyping",
           "FreeRTOS is helpful but not required for prototyping")),
    ("FreeRTOS is advantageous, not mandatory.", replace(skill("FreeRTOS", EXPLICIT, EXPLICIT),
                                                           type=T.RESPONSIBILITY)),
    ("FreeRTOS is advantageous, not mandatory.", replace(skill("FreeRTOS", EXPLICIT, EXPLICIT),
                                                           importance=I.BONUS)),
])
def test_does_not_weaken_compound_different_unbound_or_ambiguous_requirements(description, candidate):
    output = JobRequirementExtractionOutput((candidate,))
    assert preserve_explicit_optional_skill(description, output) == (output, ())
