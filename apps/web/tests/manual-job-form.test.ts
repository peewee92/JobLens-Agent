import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {ManualJobForm} from "../components/manual-job-form";

test("a pasted posting needs no extension, link, or model call to be saved", () => {
  const html = renderToStaticMarkup(React.createElement(ManualJobForm));
  assert.match(html, /粘贴一个目标岗位/);
  assert.match(html, /不调用模型/);
  assert.match(html, /手动粘贴/);
  assert.match(html, /原始岗位链接（可选）/);
  assert.match(html, /name="description"/);
  assert.match(html, /maxLength="50000"/);
  const linkInput = html.match(/<input[^>]*name="sourceUrl"[^>]*>/)?.[0] ?? "";
  assert.ok(linkInput);
  assert.doesNotMatch(linkInput, /required/);
});
