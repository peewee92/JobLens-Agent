"""Prepare one accepted Collector dataset for Requirement manual review."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.application.job_imports import ImportJobsUseCase
from app.application.job_requirements.use_cases import ExtractJobRequirementsUseCase
from app.application.requirement_acceptance import (
    InvalidRequirementAcceptanceDatasetError,
    PrepareRequirementAcceptanceBatchUseCase,
    RequirementAcceptanceCanaryGateError,
    RequirementAcceptanceImportError,
    preflight_requirement_acceptance_dataset,
)
from app.application.requirement_reviews.use_cases import (
    CreateRequirementReviewBatchUseCase,
)
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.llm import build_job_requirement_extractor
from app.repositories import (
    SqlAlchemyJobImportQueryRepository,
    SqlAlchemyJobQueryRepository,
    SqlAlchemyJobRequirementQueryRepository,
    SqlAlchemyJobRequirementUnitOfWork,
    SqlAlchemyRequirementAcceptanceRunQueryRepository,
    SqlAlchemyRequirementAcceptanceRunUnitOfWork,
    SqlAlchemyRequirementReviewQueryRepository,
    SqlAlchemyRequirementReviewUnitOfWork,
    SqlAlchemyTraceUnitOfWork,
    SqlAlchemyUnitOfWork,
)
from app.workflows.job_requirement_extraction import (
    EXTRACTOR_VERSION,
    PROMPT_VERSION,
    SEMANTIC_POLICY_VERSION,
    ExtractJobRequirementsWorkflow,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--reviewer")
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Validate and fingerprint the dataset without DB writes or provider calls.",
    )
    parser.add_argument(
        "--max-new-extractions",
        type=int,
        help="Limit actual new provider calls in this invocation; reuse does not consume it.",
    )
    parser.add_argument("--title")
    parser.add_argument(
        "--allow-fixture",
        action="store_true",
        help="Allow deterministic fixture extraction for engineering smoke only.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a machine-readable summary.",
    )
    return parser.parse_args()


def _load_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise InvalidRequirementAcceptanceDatasetError(
            f"Dataset file was not found: {path}"
        ) from error
    except (OSError, json.JSONDecodeError) as error:
        raise InvalidRequirementAcceptanceDatasetError(
            f"Dataset file could not be read as JSON: {type(error).__name__}"
        ) from error
    if not isinstance(payload, dict):
        raise InvalidRequirementAcceptanceDatasetError(
            "Dataset root must be a JSON object"
        )
    return payload


def _default_title(payload: dict[str, Any], path: Path) -> str:
    generated_at = payload.get("generatedAt")
    if isinstance(generated_at, str) and generated_at.strip():
        return f"Requirement acceptance {generated_at.strip()}"
    return f"Requirement acceptance {path.stem}"


def _build_use_case():
    settings = get_settings()
    provider = settings.requirement_extractor_provider.strip().casefold() or "disabled"
    extractor = build_job_requirement_extractor(settings)
    jobs = SqlAlchemyJobQueryRepository(SessionLocal)
    requirements = SqlAlchemyJobRequirementQueryRepository(SessionLocal)
    acceptance_runs = SqlAlchemyRequirementAcceptanceRunQueryRepository(SessionLocal)
    reviews = SqlAlchemyRequirementReviewQueryRepository(SessionLocal)
    workflow = ExtractJobRequirementsWorkflow(
        extractor,
        lambda: SqlAlchemyTraceUnitOfWork(SessionLocal),
    )
    extract = ExtractJobRequirementsUseCase(
        jobs=jobs,
        workflow=workflow,
        uow_factory=lambda: SqlAlchemyJobRequirementUnitOfWork(SessionLocal),
        query_repository=requirements,
        provider=provider,
    )
    create_batch = CreateRequirementReviewBatchUseCase(
        reviews,
        lambda: SqlAlchemyRequirementReviewUnitOfWork(SessionLocal),
    )
    use_case = PrepareRequirementAcceptanceBatchUseCase(
        import_jobs=ImportJobsUseCase(lambda: SqlAlchemyUnitOfWork(SessionLocal)),
        imports=SqlAlchemyJobImportQueryRepository(SessionLocal),
        jobs=jobs,
        requirements=requirements,
        extract_requirements=extract,
        acceptance_runs=acceptance_runs,
        acceptance_run_uow_factory=lambda: SqlAlchemyRequirementAcceptanceRunUnitOfWork(
            SessionLocal
        ),
        reviews=reviews,
        create_batch=create_batch,
        provider=provider,
        model=extractor.model_name,
        extractor_version=EXTRACTOR_VERSION,
        prompt_version=PROMPT_VERSION,
        semantic_policy_version=SEMANTIC_POLICY_VERSION,
    )
    return use_case, settings


def _provider_guard_error(
    provider: str,
    *,
    allow_fixture: bool,
    model: str = "",
    api_key: str | None = None,
    max_new_extractions: int | None = None,
) -> str | None:
    if provider == "disabled":
        return (
            "Requirement extractor is disabled. Configure "
            "REQUIREMENT_EXTRACTOR_PROVIDER=fixture or openai."
        )
    if provider == "fixture" and not allow_fixture:
        return (
            "Fixture extraction is engineering evidence only. Pass --allow-fixture "
            "explicitly, or configure the live OpenAI provider."
        )
    if provider == "openai" and (not model.strip() or not api_key):
        return (
            "OpenAI Requirement extraction requires OPENAI_API_KEY and a non-blank "
            "REQUIREMENT_EXTRACTOR_MODEL before any Job is imported."
        )
    if provider == "openai" and max_new_extractions is None:
        return (
            "OpenAI Requirement extraction requires an explicit "
            "--max-new-extractions limit. Start with 1-3 canary Jobs, then rerun "
            "the same dataset/title/reviewer to resume."
        )
    return None


def _preflight_dict(preflight) -> dict[str, Any]:
    return {
        "datasetFingerprint": preflight.dataset_fingerprint,
        "sourceVersion": preflight.source_version,
        "generatedAt": preflight.generated_at,
        "selectedCount": preflight.selected_count,
        "totalDescriptionCharacters": preflight.total_description_characters,
        "minimumDescriptionCharacters": preflight.minimum_description_characters,
        "maximumDescriptionCharacters": preflight.maximum_description_characters,
        "averageDescriptionCharacters": preflight.average_description_characters,
        "dbWrites": 0,
        "providerCalls": 0,
    }


def _summary_dict(result) -> dict[str, Any]:
    return {
        "runId": result.run_id,
        "datasetFingerprint": result.dataset_fingerprint,
        "importId": result.import_id,
        "sourceVersion": result.source_version,
        "received": result.received,
        "createdJobs": result.created_jobs,
        "updatedJobs": result.updated_jobs,
        "reusedExtractions": result.reused_extractions,
        "createdExtractions": result.created_extractions,
        "failedExtractions": result.failed_extractions,
        "deferredExtractions": result.deferred_extractions,
        "maxNewExtractions": result.max_new_extractions,
        "provider": result.provider,
        "model": result.model,
        "extractorVersion": result.extractor_version,
        "promptVersion": result.prompt_version,
        "batchId": result.batch_id,
        "batchReused": result.batch_reused,
        "readyForManualReview": result.ready_for_manual_review,
        "cases": [
            {
                "inputIndex": case.input_index,
                "jobId": case.job_id,
                "title": case.title,
                "company": case.company,
                "status": case.status.value,
                "extractionId": case.extraction_id,
                "traceRunId": case.trace_run_id,
                "errorCode": case.error_code,
                "errorMessage": case.error_message,
            }
            for case in result.cases
        ],
    }


def main() -> int:
    args = _arguments()
    try:
        payload = _load_payload(args.dataset)
        if args.preflight:
            preflight = preflight_requirement_acceptance_dataset(payload)
            summary = _preflight_dict(preflight)
            if args.json:
                print(json.dumps(summary, ensure_ascii=False, indent=2))
            else:
                print(
                    "Requirement acceptance preflight "
                    f"fingerprint={preflight.dataset_fingerprint} "
                    f"version={preflight.source_version} jobs={preflight.selected_count} "
                    f"characters={preflight.total_description_characters} "
                    "dbWrites=0 providerCalls=0"
                )
            return 0
        if not args.reviewer or not args.reviewer.strip():
            print("--reviewer is required unless --preflight is used.")
            return 2
        use_case, settings = _build_use_case()
        provider = settings.requirement_extractor_provider.strip().casefold() or "disabled"
        guard_error = _provider_guard_error(
            provider,
            allow_fixture=args.allow_fixture,
            model=settings.requirement_extractor_model,
            api_key=settings.openai_api_key,
            max_new_extractions=args.max_new_extractions,
        )
        if guard_error is not None:
            print(guard_error)
            return 2
        result = use_case.execute(
            payload=payload,
            title=(args.title or _default_title(payload, args.dataset)),
            reviewer=args.reviewer,
            max_new_extractions=args.max_new_extractions,
        )
    except (
        InvalidRequirementAcceptanceDatasetError,
        RequirementAcceptanceCanaryGateError,
        RequirementAcceptanceImportError,
    ) as error:
        print(f"Preparation rejected: {error}")
        return 2

    summary = _summary_dict(result)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            "Requirement acceptance preparation "
            f"run={result.run_id} fingerprint={result.dataset_fingerprint} "
            f"import={result.import_id} provider={result.provider} model={result.model} "
            f"jobs={result.received} extracted={result.created_extractions} "
            f"reused={result.reused_extractions} failed={result.failed_extractions} "
            f"deferred={result.deferred_extractions} "
            f"maxNewExtractions={result.max_new_extractions or 'all'} "
            f"batch={result.batch_id or 'none'} batchReused={result.batch_reused}"
        )
        for case in result.cases:
            if case.error_code:
                print(
                    f"- [{case.input_index + 1}] {case.title} / {case.company}: "
                    f"{case.error_code}; trace={case.trace_run_id or 'none'}; "
                    f"{case.error_message or 'unknown failure'}"
                )
        if result.provider == "fixture":
            print(
                "Fixture Batch validates orchestration only; it is not formal model-quality evidence."
            )
        if result.ready_for_manual_review:
            print(
                "Open /evals/requirements/manual and perform all case judgments manually."
            )
        else:
            print(
                "No Review Batch was created. Rerun the same dataset/title/reviewer "
                "after fixing failures or to continue deferred cases; same-input "
                "same-cohort successes will be reused."
            )
    return 0 if result.ready_for_manual_review else 1


if __name__ == "__main__":
    raise SystemExit(main())
