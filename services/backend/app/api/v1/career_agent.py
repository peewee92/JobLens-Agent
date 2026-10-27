from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder

from app.agent.entrypoint import CareerAgentEntrypointError
from app.agent.graph.hitl_decision import HumanDecisionError
from app.agent.graph.checkpoint_port import CheckpointConflictError
from app.agent.graph.hitl_service import CareerAgentHitlService
from app.agent.runtimes import CareerAgentRuntime
from app.api.deps import get_career_agent_hitl_service, get_career_agent_runtime
from app.api.v1.schemas.career_agent import (
    CareerAgentResumeRequest,
    CareerAgentRunRequest,
    CareerAgentRunStateResponse,
    CareerAgentRunListResponse,
    CareerAgentTurnRequest,
    ContinueAnalysisRequest,
)

router = APIRouter(prefix="/career-agent")


@router.post("/turn")
def run_career_agent_turn(
    payload: CareerAgentTurnRequest,
    runtime: CareerAgentRuntime = Depends(get_career_agent_runtime),
) -> object:
    try:
        result = runtime.run(payload.to_command())
    except CareerAgentEntrypointError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return jsonable_encoder(result)


@router.post("/runs")
def start_career_agent_run(
    payload: CareerAgentRunRequest,
    service: CareerAgentHitlService = Depends(get_career_agent_hitl_service),
) -> object:
    try:
        state = service.start(payload.to_command())
    except CheckpointConflictError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return jsonable_encoder(CareerAgentRunStateResponse.from_state(state))


@router.get("/runs")
def list_career_agent_runs(
    limit: int = Query(default=10, ge=1, le=20),
    service: CareerAgentHitlService = Depends(get_career_agent_hitl_service),
) -> object:
    return jsonable_encoder(CareerAgentRunListResponse(items=[
        CareerAgentRunStateResponse.from_state(state) for state in service.recent_runs(limit=limit)
    ]))


@router.get("/runs/{thread_id}")
def get_career_agent_run(
    thread_id: str,
    service: CareerAgentHitlService = Depends(get_career_agent_hitl_service),
) -> object:
    state = service.get_state(thread_id=thread_id)
    if state is None:
        raise HTTPException(status_code=404, detail="career agent thread does not exist")
    return jsonable_encoder(CareerAgentRunStateResponse.from_state(state))


@router.post("/runs/{thread_id}/resume")
def resume_career_agent_run(
    thread_id: str,
    payload: CareerAgentResumeRequest,
    service: CareerAgentHitlService = Depends(get_career_agent_hitl_service),
) -> object:
    try:
        state = service.resume(payload.to_command(thread_id=thread_id))
    except HumanDecisionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CheckpointConflictError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return jsonable_encoder(CareerAgentRunStateResponse.from_state(state))


@router.post("/runs/{thread_id}/continue")
def continue_career_agent_run(
    thread_id: str,
    payload: ContinueAnalysisRequest | None = None,
    service: CareerAgentHitlService = Depends(get_career_agent_hitl_service),
) -> object:
    if service.get_state(thread_id=thread_id) is None:
        raise HTTPException(status_code=404, detail="career agent thread does not exist")
    try:
        state = service.continue_run(thread_id=thread_id, update_command=payload.to_command() if payload else None)
    except CheckpointConflictError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"error": {"code": "analysis_continue_save_uncertain",
            "message": "继续分析未能返回完整状态，请查看运行并重试原分批请求，不要创建新请求。",
            "retryable": True, "repairAction": "check_then_retry_original",
            "correlationId": payload.action_id if payload else thread_id}})
    return jsonable_encoder(CareerAgentRunStateResponse.from_state(state))


@router.get("/runs/{thread_id}/result")
def get_saved_career_analysis(
    thread_id: str,
    service: CareerAgentHitlService = Depends(get_career_agent_hitl_service),
) -> object:
    from app.api.v1.schemas.career_analysis import SavedCareerAnalysisResponse
    if service.get_state(thread_id=thread_id) is None:
        raise HTTPException(status_code=404, detail="career agent thread does not exist")
    result = service.get_result(thread_id=thread_id)
    if result is None:
        raise HTTPException(status_code=404, detail="此运行没有保存完整分析结果；旧指纹不能还原历史材料，请新建分析")
    return jsonable_encoder(SavedCareerAnalysisResponse.from_result(result, service.result_stale_reasons(result), service.get_state(thread_id=thread_id)))


from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from app.api.deps import get_start_analysis_execution_use_case, get_analysis_execution_query
from app.api.v1.schemas.analysis_execution import (
    StartAnalysisExecutionRequest, AnalysisExecutionResponse, AnalysisExecutionStatusResponse,
)
from app.application.application_workspace.start_analysis_execution import StartAnalysisExecutionError
from app.agent.graph.checkpoint_port import CheckpointPersistenceError

_EXECUTION_ERRORS = {
    "analysis_execution_command_conflict": ("这个请求标识已用于不同内容，请查看原执行结果。", "check_original_request"),
    "analysis_execution_result_missing": ("没有找到这份已保存结果，请返回运行查看。", "open_run"),
    "analysis_execution_not_completed": ("本次分析尚未完成或已过期，不能建立新准备材料。", "review_analysis"),
    "analysis_execution_selection_invalid": ("只能选择本次已经确认的 1～5 个目标岗位。", "select_confirmed_jobs"),
    "analysis_execution_facts_stale": ("分析使用的事实已变化，请保留旧结果并更新分析后再开始执行。", "update_analysis"),
    "analysis_execution_materials_unusable": ("本次准备材料不可用，请查看分析阻断后重新分析。", "review_analysis"),
}


@router.post("/runs/{thread_id}/execution", response_model=AnalysisExecutionResponse)
def start_analysis_execution(thread_id: str, payload: StartAnalysisExecutionRequest,
                             use_case=Depends(get_start_analysis_execution_use_case)):
    try:
        return AnalysisExecutionResponse.from_result(use_case.execute(payload.to_command(thread_id)))
    except StartAnalysisExecutionError as exc:
        message, action = _EXECUTION_ERRORS[exc.code]
        return JSONResponse(status_code=409, content={"error": {"code": exc.code, "message": message,
            "retryable": False, "repairAction": action, "correlationId": payload.command_id}})
    except (CheckpointPersistenceError, SQLAlchemyError):
        return JSONResponse(status_code=503, content={"error": {"code": "analysis_execution_save_failed",
            "message": "开始执行未能保存。请先查看已有工作区，再使用同一个原请求重试；不要创建新请求。",
            "retryable": True, "repairAction": "check_then_retry_original", "correlationId": payload.command_id}})


@router.get("/runs/{thread_id}/execution", response_model=AnalysisExecutionStatusResponse)
def get_analysis_execution(thread_id: str, query=Depends(get_analysis_execution_query)):
    execution = query.for_thread(thread_id)
    return AnalysisExecutionStatusResponse(execution=AnalysisExecutionResponse.from_result(execution) if execution else None)


from typing import Literal
from app.api.deps import get_analysis_update_plan_use_case
from app.api.v1.schemas.analysis_update import AnalysisUpdatePlanResponse
from app.application.analysis_update import AnalysisUpdatePlanError


@router.get('/runs/{thread_id}/update-plan', response_model=AnalysisUpdatePlanResponse)
def get_analysis_update_plan(thread_id: str, scope: Literal['targets', 'batch'] = Query(default='targets'),
                             use_case=Depends(get_analysis_update_plan_use_case)):
    try:
        return AnalysisUpdatePlanResponse.from_result(use_case.execute(thread_id=thread_id, scope=scope))
    except SQLAlchemyError as exc:
        from app.agent.graph.checkpoint_port import CheckpointNotReadyError
        raise CheckpointNotReadyError('更新预检无法读取数据库，请检查就绪接口并在副本验证迁移后重试；没有启动更新。') from exc
    except AnalysisUpdatePlanError as exc:
        raise HTTPException(status_code=404 if str(exc) == 'analysis_update_result_missing' else 409,
                            detail=str(exc)) from exc


from app.api.v1.schemas.analysis_update import StartAnalysisUpdateRequest


@router.post('/runs/{thread_id}/updates', response_model=CareerAgentRunStateResponse)
def start_analysis_update(thread_id: str, payload: StartAnalysisUpdateRequest,
                          service=Depends(get_career_agent_hitl_service)):
    try:
        return CareerAgentRunStateResponse.from_state(service.start_update(payload.to_command(thread_id)))
    except AnalysisUpdatePlanError as exc:
        return JSONResponse(status_code=409, content={"error": {"code": "analysis_update_source_unavailable",
            "message": "原结果不可读取，请返回历史运行核对；未替换原结果。", "retryable": False,
            "repairAction": "review_original", "correlationId": payload.request_id}})
    except CheckpointConflictError as exc:
        return JSONResponse(status_code=409, content={"error": {"code": "analysis_update_conflict",
            "message": str(exc), "retryable": False, "repairAction": "review_run_or_preflight",
            "correlationId": payload.request_id}})
    except (SQLAlchemyError, CheckpointPersistenceError):
        return JSONResponse(status_code=503, content={"error": {"code": "analysis_update_save_uncertain",
            "message": "更新未能返回完整状态。请查看运行或用同一个原请求重试，不要创建新请求。",
            "retryable": True, "repairAction": "check_then_retry_original", "correlationId": payload.request_id}})


from app.api.deps import get_analysis_comparison_use_case
from app.api.v1.schemas.analysis_comparison import AnalysisComparisonResponse
from app.application.analysis_comparison import AnalysisComparisonError

_COMPARISON_ERRORS = {
    'analysis_comparison_run_missing': '没有找到本次运行，请从最近分析中重新打开。',
    'analysis_comparison_result_missing': '本次或原分析尚未保存完整结果；请查看运行并完成确认，不会用实时计算冒充历史。',
    'analysis_comparison_not_update': '这不是带有原结果引用的更新分析，不能自行选择另一份报告冒充本次来源。',
    'analysis_comparison_source_missing': '原分析结果不可读取，无法还原本次更新的历史来源；当前结果仍保留。',
    'analysis_comparison_binding_invalid': '保存结果与历史报告的身份不一致，已停止比较；请核对原运行，不会改用最新报告。',
    'analysis_comparison_scope_invalid': '新旧运行的岗位范围无法核对，已停止比较；请分别查看两次保存结果。',
}


@router.get('/runs/{thread_id}/comparison', response_model=AnalysisComparisonResponse)
def get_analysis_comparison(thread_id: str, use_case=Depends(get_analysis_comparison_use_case)):
    try:
        return AnalysisComparisonResponse.from_result(use_case.execute(thread_id=thread_id))
    except AnalysisComparisonError as exc:
        return JSONResponse(status_code=404 if exc.code == 'analysis_comparison_run_missing' else 409,
            content={'error': {'code': exc.code, 'message': _COMPARISON_ERRORS[exc.code], 'retryable': False,
                               'repairAction': 'review_saved_results', 'correlationId': thread_id}})
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={'error': {'code': 'analysis_comparison_storage_unavailable',
            'message': '历史结果暂时无法读取，请检查后端和数据库后重试；没有执行更新或改写结果。',
            'retryable': True, 'repairAction': 'check_storage_then_retry_read', 'correlationId': thread_id}})
