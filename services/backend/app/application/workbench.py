"""Read projection only: next steps are derived, never stored as business progress."""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class WorkbenchAction:
    code: str
    label: str
    reason: str
    href: str


@dataclass(frozen=True)
class WorkbenchRun:
    thread_id: str
    status: str
    current_step: str
    job_count: int
    target_count: int
    execution_target_count: int
    result_id: str | None
    result_is_current: bool | None
    updated_at: datetime
    partial: bool = False
    completed_report_count: int = 0


@dataclass(frozen=True)
class WorkbenchWorkspace:
    workspace_id: str
    job_id: str
    title: str
    status: str
    open_action_count: int
    current_analysis_thread_id: str | None


@dataclass(frozen=True)
class WorkbenchChange:
    kind: str
    occurred_at: datetime
    href: str


@dataclass(frozen=True)
class WorkbenchSnapshot:
    profile_version: int | None
    search_intent_version: int | None
    evidence_count: int
    input_issue_codes: tuple[str, ...]
    job_count: int
    current_run: WorkbenchRun | None
    workspaces: tuple[WorkbenchWorkspace, ...]
    changes: tuple[WorkbenchChange, ...]


@dataclass(frozen=True)
class Workbench:
    snapshot: WorkbenchSnapshot
    next_action: WorkbenchAction


class WorkbenchQuery(Protocol):
    def read(self) -> WorkbenchSnapshot: ...


class GetWorkbenchUseCase:
    def __init__(self, query: WorkbenchQuery):
        self._query = query

    def execute(self) -> Workbench:
        view = self._query.read()
        run = view.current_run
        from urllib.parse import quote
        run_href = f"/agent?threadId={quote(run.thread_id, safe='')}" if run else "/agent"
        if view.input_issue_codes:
            action = WorkbenchAction("confirm_inputs", "确认我的资料和意向", "只使用已确认事实；请先处理下方具体输入问题。仍可浏览岗位。", "/profile")
        elif not view.job_count:
            action = WorkbenchAction("add_jobs", "添加岗位", "先导入真实岗位，再检查要求与分析输入。", "/import")
        elif run and run.status in {"created", "running", "resuming", "interrupted"}:
            action = WorkbenchAction("open_run", "确认目标岗位" if run.status == "interrupted" else "查看当前分析", "打开只查看状态；继续执行必须由你显式操作。", run_href)
        elif run and run.result_id and run.result_is_current is False:
            action = WorkbenchAction("review_stale_analysis", "查看变化并准备更新分析", "事实已变化；保留旧材料，先核对变化，不会自动再次调用模型。", f"/agent/results/{quote(run.thread_id, safe='')}")
        elif run and run.result_id and run.target_count > run.execution_target_count:
            action = WorkbenchAction("start_execution", "开始执行目标岗位", "打开原分析，一次建立工作区、准备材料与行动。", f"/agent/results/{quote(run.thread_id, safe='')}")
        elif run and run.status in {"blocked", "failed", "stale"}:
            action = WorkbenchAction("repair_run", "查看分析阻断和修复入口", "保留已经完成的结果，先核对失败原因。", run_href)
        elif view.workspaces:
            action = WorkbenchAction("continue_execution", "继续岗位准备", "优先完成已有行动；真实投递结果由你手动记录。", f"/applications/{quote(view.workspaces[0].workspace_id, safe='')}")
        else:
            action = WorkbenchAction("analyze_jobs", "选择岗位并检查分析输入", "最多选择 50 个岗位；只读比较已有报告，缺少输入时先修复。", "/agent")
        return Workbench(view, action)
