import test from "node:test";
import assert from "node:assert/strict";
import {appendAgentJobPage} from "../lib/agent-job-pages";
import type {JobListItem, JobPage} from "../lib/contracts";
const job = (id: string) => ({id, title: id, company: "fixture"}) as JobListItem;
const page = (offset: number, ids: string[], total: number): JobPage => ({offset, limit:20, total, items:ids.map(job)});
test("paging preserves pinned and selected identities, skips duplicates, and uses server offset", () => {
 const initial=[job("pinned"),...Array.from({length:20},(_,i)=>job(`j${i}`))];
 const next=appendAgentJobPage(initial,page(20,["pinned","j20","j21"],40),20);
 assert.equal(next.jobs.length,23); assert.equal(next.offset,23); assert.equal(next.hasMore,true);
 assert.equal(next.jobs[0].id,"pinned");
 assert.equal(appendAgentJobPage(next.jobs,page(23,[],23),23).hasMore,false);
 assert.throws(() => appendAgentJobPage(next.jobs,page(23,[],40),23));
});
test("rejects mismatched pages without advancing", () => {
 assert.throws(()=>appendAgentJobPage([],page(0,["j"],1),20));
});
