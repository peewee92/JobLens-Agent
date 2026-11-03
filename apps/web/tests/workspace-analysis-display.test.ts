import test from "node:test";
import assert from "node:assert/strict";
import {factAnalysisRelation, groupWorkspaceActions} from "../lib/workspace-analysis-display";
import type {ApplicationExecutionAction} from "../lib/contracts";

const action = (actionId: string, sourceAnalysisResultId: string | null, status = "todo") => ({actionId, sourceAnalysisResultId, status, actionType: "learn", createdAt: "2026-01-01"}) as ApplicationExecutionAction;

test("current and earlier actions remain distinct and retain progress", () => {
  const items = [action("old", "r1", "done"), action("current", "r2"), action("unknown", null, "in_progress")];
  const groups = groupWorkspaceActions(items, "r2");
  assert.deepEqual(groups.current.map(x => x.actionId), ["current"]);
  assert.deepEqual(groups.earlier.map(x => x.actionId), ["unknown", "old"]);
  assert.equal(groups.earlier[1].status, "done");
  assert.equal(groupWorkspaceActions(items, null).current.length, 3);
});
test("fact confirmation is compared to saved input version without asserting retention", () => {
  assert.equal(factAnalysisRelation(3, 2), "after");
  assert.equal(factAnalysisRelation(3, 3), "at_or_before");
  assert.equal(factAnalysisRelation(3, 4), "at_or_before");
  assert.equal(factAnalysisRelation(null, 4), "unknown");
  assert.equal(factAnalysisRelation(3, null), "unknown");
});

test("receipt places reused actions under current analysis without changing source or progress", async () => {
  const {currentExecutionActionIds} = await import("../lib/workspace-analysis-display");
  const reused = action("reused", "old-result", "done");
  const old = action("old", "old-result");
  const execution = {threadId: "new", resultId: "new-result", commandId: "cmd", items: [
    {jobId: "job", workspaceId: "workspace", resumeVariantId: null, actionIds: ["reused"]},
  ]};
  const ids = currentExecutionActionIds(execution, "new-result", "workspace");
  const groups = groupWorkspaceActions([reused, old], "new-result", ids);
  assert.deepEqual(groups.current.map(item => item.actionId), ["reused"]);
  assert.equal(groups.current[0].status, "done");
  assert.equal(groups.current[0].sourceAnalysisResultId, "old-result");
  assert.deepEqual(groups.earlier.map(item => item.actionId), ["old"]);
  assert.equal(currentExecutionActionIds(execution, "other", "workspace"), null);
  assert.equal(currentExecutionActionIds(execution, "new-result", "other"), null);
  assert.equal(groupWorkspaceActions([reused], "new-result", null).earlier.length, 1);
});
