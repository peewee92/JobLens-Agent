from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder

from app.agent.entrypoint import CareerAgentEntrypoint, CareerAgentEntrypointError
from app.api.deps import get_career_agent_entrypoint
from app.api.v1.schemas.career_agent import CareerAgentTurnRequest

router = APIRouter(prefix="/career-agent")


@router.post("/turn")
def run_career_agent_turn(
    payload: CareerAgentTurnRequest,
    entrypoint: CareerAgentEntrypoint = Depends(get_career_agent_entrypoint),
) -> object:
    try:
        result = entrypoint.execute(payload.to_command())
    except CareerAgentEntrypointError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return jsonable_encoder(result)
