"""No commands, model calls, or hidden continuation on this GET route."""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from app.api.deps import get_workbench_use_case, get_workbench_query
from app.api.v1.schemas.workbench import WorkbenchResponse, WorkbenchWorkspacePageResponse
from dataclasses import asdict
from app.application.workbench import GetWorkbenchUseCase

router = APIRouter()


@router.get("/workbench", response_model=WorkbenchResponse)
def get_workbench(use_case: GetWorkbenchUseCase = Depends(get_workbench_use_case)):
    try:
        return WorkbenchResponse.from_result(use_case.execute())
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"error": {
            "code": "workbench_unavailable", "message": "暂时无法读取工作台，请检查数据库和迁移状态后刷新。",
            "retryable": True, "repairAction": "check_database_and_retry", "correlationId": "workbench-read"}})


@router.get("/workbench/workspaces", response_model=WorkbenchWorkspacePageResponse)
def list_workspaces(offset: int = Query(default=0, ge=0, le=100000), query=Depends(get_workbench_query)):
    try:
        items, has_more = query.list_workspaces(offset=offset, limit=20)
        return WorkbenchWorkspacePageResponse(items=[asdict(item) for item in items], offset=offset, has_more=has_more)
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"error": {
            "code": "workbench_unavailable", "message": "暂时无法读取工作区，请检查数据库后重试。",
            "retryable": True, "repairAction": "check_database_and_retry", "correlationId": "workbench-workspaces"}})
