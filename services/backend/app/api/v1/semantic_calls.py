"""Read-only preview and explicitly authorized matching; GET never executes a model."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from app.api.deps import get_authorized_semantic_match
from app.api.v1.schemas.semantic_calls import SemanticCallCommand, SemanticCallPlan, SemanticCallRecord
from app.application.job_requirements.call_models import RequirementCallConflict
from app.application.job_queries.errors import JobNotFoundError
from app.application.job_availability_guard import JobUnavailableForMatchingError
from app.application.eligibility.errors import EligibilityInputsNotReadyError
from app.application.evidence_retrieval.errors import EvidenceRetrievalInputsNotReadyError
from app.application.semantic_match.errors import SemanticMatchInputsNotReadyError

router = APIRouter(prefix="/jobs")
INPUT_ERRORS = (JobUnavailableForMatchingError, EligibilityInputsNotReadyError, EvidenceRetrievalInputsNotReadyError, SemanticMatchInputsNotReadyError)


def conflict(code, action_id=None):
    return JSONResponse({"error": {"code": code, "message": "本次匹配未执行，请核对资料、岗位要求、授权范围与原请求状态。",
        "retryable": False, "repairAction": "review_match_plan", "correlationId": action_id}}, status_code=409)


@router.get("/{job_id}/semantic-call-plan", response_model=SemanticCallPlan)
def plan(job_id: str, service=Depends(get_authorized_semantic_match)):
    try:
        return service.plan(job_id)[0]
    except JobNotFoundError:
        return JSONResponse({"error": {"code": "job_not_found", "message": "岗位不存在。"}}, status_code=404)
    except INPUT_ERRORS:
        return conflict("match_inputs_not_ready")
    except SQLAlchemyError:
        return JSONResponse({"error": {"code": "semantic_storage_unavailable", "message": "暂时无法读取匹配请求记录，请检查数据库迁移或稍后重试。", "retryable": True, "repairAction": "check_readiness"}}, status_code=503)


@router.get("/{job_id}/semantic-calls/{action_id}", response_model=SemanticCallRecord)
def status(job_id: str, action_id: str, service=Depends(get_authorized_semantic_match)):
    record = service.journal.get(job_id, action_id)
    if record is None:
        return JSONResponse({"error": {"code": "semantic_call_not_found", "message": "未找到这次匹配请求。"}}, status_code=404)
    return record


@router.post("/{job_id}/semantic-calls", response_model=SemanticCallRecord)
def execute(job_id: str, command: SemanticCallCommand, service=Depends(get_authorized_semantic_match)):
    try:
        return service.execute(job_id, command)
    except JobNotFoundError:
        return JSONResponse({"error": {"code": "job_not_found", "message": "岗位不存在。"}}, status_code=404)
    except RequirementCallConflict as exc:
        return conflict(str(exc), command.action_id)
    except INPUT_ERRORS:
        return conflict("match_inputs_not_ready", command.action_id)
    except SQLAlchemyError:
        return JSONResponse({"error": {"code": "semantic_call_save_uncertain", "message": "保存状态不确定，请查询原请求，不要重新授权。",
            "retryable": True, "repairAction": "get_semantic_call", "correlationId": command.action_id}}, status_code=503)
