import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {ImportUpdatedNotice} from "../components/import-updated-notice";
import type {JobImportAuditItem} from "../lib/contracts";

function item(outcome: JobImportAuditItem["outcome"], jobId: string | null, inputIndex: number): JobImportAuditItem {
  return {outcome, jobId, inputIndex, jobSourceId: null, errorCode: null, errorMessage: null};
}

test("updated observations are deduplicated, linked, and not claimed as history", () => {
  const items = [item("created", "a", 0), item("updated", "a", 1), item("updated", "a", 2), item("updated", "b", 3)];
  const html = renderToStaticMarkup(React.createElement(ImportUpdatedNotice, {items, labels: {a: "工程师 · 公司"}}));
  assert.match(html, /有 2 个已有岗位/);
  assert.match(html, /较短的内容不一定更准确/);
  assert.match(html, /并非当时的历史快照/);
  assert.match(html, /工程师 · 公司/);
  assert.match(html, /岗位 b/);
  assert.equal((html.match(/href="\/jobs\/a"/g) ?? []).length, 1);
});

test("no successful updated observation means no update notice", () => {
  const items = [item("created", "a", 0), item("updated", null, 1)];
  assert.equal(renderToStaticMarkup(React.createElement(ImportUpdatedNotice, {items, labels: {}})), "");
});
