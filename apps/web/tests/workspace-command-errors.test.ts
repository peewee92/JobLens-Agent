import test from "node:test";
import assert from "node:assert/strict";
import {workspaceCommandError} from "../lib/workspace-command-errors";

test("transaction failure keeps the backend repair instruction visible", () => {
  const message = "请刷新查看原记录后使用原操作重试";
  assert.equal(workspaceCommandError({error: {code: "workspace_transaction_save_failed", message, retryable: true}}), message);
});
test("stale profile and concurrent manual state updates have distinct repair instructions", () => {
  assert.match(workspaceCommandError({detail: "evidence_proposal_profile_stale"}), /不能直接确认旧提案/);
  assert.match(workspaceCommandError({detail: "execution_action_status_conflict"}), /刷新后按当前状态/);
  assert.match(workspaceCommandError({detail: "application_status_conflict"}), /投递状态/);
  assert.doesNotMatch(workspaceCommandError({detail: "private_database_exception"}), /private/);
});
test("malformed and network errors do not become a false success", () => {
  assert.match(workspaceCommandError(null), /操作未完成/);
  assert.match(workspaceCommandError({detail: [{type: "missing"}]}), /操作未完成/);
});
