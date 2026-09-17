from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder

from app.agent.entrypoint import CareerAgentEntrypointError
from app.agent.runtimes import CareerAgentRuntime
from app.api.deps import get_career_agent_runtime
from app.api.v1.schemas.career_agent import CareerAgentTurnRequest

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
