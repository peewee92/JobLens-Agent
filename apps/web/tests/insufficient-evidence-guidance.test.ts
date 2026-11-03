import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {InsufficientEvidenceGuidance} from "../components/insufficient-evidence-guidance";
import type {MatchReportRequirementResult} from "../lib/contracts";
const item: MatchReportRequirementResult = {requirementId:'req1', requirementIndex:0, type:'skill', importance:'must_have', originalText:'熟悉示例工具', normalizedCapability:'示例', eligibilityStatus:'conditional', semanticVerdict:'not_matched', evidenceIds:[], profileFactRefs:[], reason:'已提供的经历未覆盖此要求'};
test('shows saved requirement and avoids inventing ability or confirmed fact', () => {
 const html = renderToStaticMarkup(React.createElement(InsufficientEvidenceGuidance,{requirements:[item]}));
 assert.match(html,/熟悉示例工具/); assert.match(html,/已提供的经历未覆盖此要求/); assert.match(html,/不等于你不会/); assert.match(html,/行动完成不会自动成为职业经历/);
});
test('empty saved details do not invent gaps', () => {
 const html = renderToStaticMarkup(React.createElement(InsufficientEvidenceGuidance,{requirements:[]}));
 assert.match(html,/没有保存可逐项展示的待核实要求/);
});
