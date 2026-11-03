import type {AnalysisExecutionResult, ApplicationExecutionAction} from "./contracts";
import {prioritizeApplicationActions} from "./application-actions";

/** Receipts record reuse without rewriting the action's original source. */
export function currentExecutionActionIds(execution: AnalysisExecutionResult | null, resultId: string, workspaceId: string): string[] | null {
  if (!execution || execution.resultId !== resultId) return null;
  const item = execution.items.find(item => item.workspaceId === workspaceId);
  return item ? item.actionIds : null;
}

export function groupWorkspaceActions(actions: readonly ApplicationExecutionAction[], currentResultId?: string | null, currentActionIds?: readonly string[] | null) {
  const ordered = prioritizeApplicationActions(actions);
  if (!currentResultId) return {current: ordered, earlier: [] as ApplicationExecutionAction[]};
  const applicable = currentActionIds == null ? null : new Set(currentActionIds);
  const isCurrent = (action: ApplicationExecutionAction) =>
    action.sourceAnalysisResultId === currentResultId || Boolean(applicable?.has(action.actionId));
  return {current: ordered.filter(isCurrent), earlier: ordered.filter(action => !isCurrent(action))};
}

/** Version ordering describes the analysis input, not proof that a later edit retained the fact. */
export function factAnalysisRelation(confirmedVersion: number | null, analysisVersion: number | null | undefined): "after" | "at_or_before" | "unknown" {
  if (confirmedVersion == null || analysisVersion == null) return "unknown";
  return confirmedVersion > analysisVersion ? "after" : "at_or_before";
}
