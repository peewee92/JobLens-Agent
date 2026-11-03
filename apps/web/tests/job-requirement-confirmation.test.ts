import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {AppRouterContext} from "next/dist/shared/lib/app-router-context.shared-runtime";
import {JobRequirementConfirmation} from "../components/job-requirement-confirmation";

function render(confirmed: boolean) {
  return renderToStaticMarkup(React.createElement(AppRouterContext.Provider,
    {value: {refresh() {}} as never}, React.createElement(JobRequirementConfirmation, {
      jobId: "job", extractionId: "extract", inputHash: "a".repeat(64), factsDigest: "b".repeat(64), confirmed,
    })));
}

test("confirmation is opt-in and limited to the current extraction", () => {
  const html = render(false);
  assert.match(html, /核对这一个岗位/);
  assert.match(html, /不替维护者签署模型质量评审/);
  assert.match(html, /不调用模型/);
  assert.match(html, /<button[^>]*disabled/);
});

test("existing confirmation is shown without resubmitting", () => {
  const html = render(true);
  assert.match(html, /你已核对这份岗位要求/);
  assert.match(html, /不代表抽取模型已通过整体质量评审/);
  assert.doesNotMatch(html, /<button|type="checkbox"/);
});
