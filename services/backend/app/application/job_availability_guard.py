"""Guard new matching without affecting historical records or manual actions."""
from app.application.ports.job_query_repository import AbstractJobQueryRepository


class JobUnavailableForMatchingError(RuntimeError):
    """The user marked a job inactive or changed its availability during analysis."""

    def __init__(self, message: str, *, code: str = "job_user_marked_inactive") -> None:
        super().__init__(message)
        self.code = code


def matching_availability_revision(jobs: AbstractJobQueryRepository, job_id: str) -> int | None:
    job = jobs.get_job(job_id)
    if job is not None and job.user_marked_inactive:
        raise JobUnavailableForMatchingError(
            "岗位已标记为失效，请先在岗位详情中恢复，或从本次分析中移除。"
        )
    return job.availability_revision if job is not None else None
