import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {RankedJobLabel} from "../components/career-agent-hitl-panel";
import type {JobListItem} from "../lib/contracts";

test("ranked target uses recovered title when the job is outside the loaded page", () => {
  const render = (label?: string, job?: JobListItem) => renderToStaticMarkup(
    React.createElement(RankedJobLabel, {jobId: "job-old", label, job}),
  );
  assert.equal(render("历史范围岗位"), "历史范围岗位");
  assert.equal(render(), "job-old");
  assert.match(render("其他名称", {id: "job-old", title: "当前岗位", company: "示例公司"} as JobListItem), /当前岗位.*示例公司/);
});
