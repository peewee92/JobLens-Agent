import test from "node:test";
import assert from "node:assert/strict";
import {batchIssueDescription, collectBatchIssues} from "../lib/batch-match-issues";
import type {BatchMatchExecutionResponse} from "../lib/contracts";
type Item = BatchMatchExecutionResponse["items"][number];
const item = (jobId: string, status: Item["status"], errorCode: string | null = null): Item => ({jobId,status,errorCode,blockerCodes:[]});

test("preserve terminal issues across rounds, ignore deferred, clear only when succeeded", () => {
 const first = collectBatchIssues([], [item("a", "failed", "semantic_model_authorization_required"),item("b", "deferred_limit"),item("c", "input_blocked")]);
 assert.deepEqual(first.map(x=>x.jobId), ["a", "c"]);
 const second = collectBatchIssues(first, [item("b", "succeeded"),item("d", "persistence_blocked")]);
 assert.deepEqual(second.map(x=>x.jobId), ["a", "c", "d"]);
 assert.match(batchIssueDescription(second[0]), /未授权/);
 assert.match(batchIssueDescription(second[1]), /核对输入/);
 assert.match(batchIssueDescription(second[2]), /数据库/);
 assert.deepEqual(collectBatchIssues(second,[item("a","succeeded")]).map(x=>x.jobId), ["c", "d"]);
});


test("availability blockers give a specific repair action", () => {
 const inactive = {...item("a", "input_blocked"), blockerCodes: ["job_user_marked_inactive"]};
 const changed = {...item("b", "input_blocked"), blockerCodes: ["job_availability_changed"]};
 assert.match(batchIssueDescription(inactive), /岗位详情中恢复/);
 assert.match(batchIssueDescription(changed), /状态发生变化/);
});
