"""Seed deterministic Requirement manual review smoke data.

This script is restricted to APP_ENV=test. The seeded decisions are not real
human quality evidence; they only exercise the review workflow.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.db.models import (
    JobORM,
    JobRequirementExtractionORM,
    JobRequirementORM,
    JobSourceORM,
    TraceSpanORM,
)
from app.db.session import SessionLocal

SAMPLE_SIZE = 20


def main() -> int:
    settings = get_settings()
    if settings.app_env != "test":
        print("Refusing to seed Requirement manual review data outside APP_ENV=test.")
        return 1

    base_time = datetime(2026, 8, 3, 8, 0, tzinfo=timezone.utc)
    records = []
    for index in range(SAMPLE_SIZE):
        job_id = f"job_manual_smoke_{index:02d}"
        trace_id = f"run_manual_smoke_{index:02d}"
        extraction_id = f"reqrun_manual_smoke_{index:02d}"
        created_at = base_time + timedelta(minutes=index)
        job = JobORM(
            id=job_id,
            canonical_key=f"manual-smoke:{index:02d}",
            title=f"AI Agent Engineer {index:02d}",
            company=f"Smoke Company {index:02d}",
            description=(
                "负责使用 Python 和 FastAPI 构建 Agent 工作流，要求具备工具调用、"
                "结构化输出、Trace 与模型质量评测经验，并能交付可验证的生产功能。"
            ),
            skills=["Python", "FastAPI", "Agent", "Trace", "Eval"],
            created_at=created_at,
            updated_at=created_at,
        )
        job.sources.append(
            JobSourceORM(
                id=f"src_manual_smoke_{index:02d}",
                source="smoke",
                source_job_id=f"manual-smoke-{index:02d}",
                source_url=f"https://example.test/jobs/{index:02d}",
                normalized_source_url=f"https://example.test/jobs/{index:02d}",
                source_version="smoke-v1",
                source_raw={"seed": "requirement-manual-review-smoke"},
                first_seen_at=created_at,
                last_seen_at=created_at,
                collected_at=created_at,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        trace = TraceSpanORM(
            id=trace_id,
            capability="requirement_extraction",
            version="requirement-extractor-v1",
            model="simulated-live-requirement-model",
            prompt_version="requirement-extraction-v1",
            input_refs={"jobId": job_id, "descriptionSha256": f"manual-smoke-{index:02d}"},
            output={"requirements": [{"normalizedCapability": "Python"}]},
            latency_ms=15,
            input_tokens=30,
            output_tokens=20,
            error=None,
            created_at=created_at,
        )
        extraction = JobRequirementExtractionORM(
            id=extraction_id,
            job_id=job_id,
            input_hash=f"manual-smoke-{index:02d}".ljust(64, "0"),
            description_characters=len(job.description or ""),
            extractor_version="requirement-extractor-v1",
            provider="simulated-live",
            model="simulated-live-requirement-model",
            prompt_version="requirement-extraction-v1",
            trace_run_id=trace_id,
            requirement_count=1,
            created_at=created_at,
        )
        extraction.requirements.append(
            JobRequirementORM(
                id=f"req_manual_smoke_{index:02d}",
                job_id=job_id,
                requirement_index=0,
                type="skill",
                original_text="要求具备 Python 和 FastAPI 开发经验",
                normalized_capability="Python",
                importance="must_have",
                evidence_span="使用 Python 和 FastAPI 构建 Agent 工作流",
                confidence=0.92,
                extractor_version="requirement-extractor-v1",
                created_at=created_at,
            )
        )
        records.extend([job, trace, extraction])

    with SessionLocal() as session:
        jobs = [item for item in records if isinstance(item, JobORM)]
        traces = [item for item in records if isinstance(item, TraceSpanORM)]
        extractions = [
            item for item in records if isinstance(item, JobRequirementExtractionORM)
        ]
        session.add_all([*jobs, *traces])
        session.flush()
        session.add_all(extractions)
        session.commit()

    print(f"Seeded {SAMPLE_SIZE} simulated-live Requirement Extractions for smoke only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
