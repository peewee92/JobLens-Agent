from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder

from app.agent.entrypoint import CareerAgentEntrypointError
from app.agent.graph.hitl_decision import HumanDecisionError
from app.agent.graph.hitl_service import CareerAgentHitlService
from app.agent.runtimes import CareerAgentRuntime
from app.api.deps import get_career_agent_hitl_service, get_career_agent_runtime
from app.api.v1.schemas.career_agent import (
    CareerAgentResumeRequest,
    CareerAgentRunRequest,
    CareerAgentRunStateResponse,
    CareerAgentTurnRequest,
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
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return jsonable_encoder(CareerAgentRunStateResponse.from_state(state))


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
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return jsonable_encoder(CareerAgentRunStateResponse.from_state(state))
