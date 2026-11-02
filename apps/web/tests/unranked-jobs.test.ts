import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import test from "node:test";
import assert from "node:assert/strict";
import {UnrankedJobs} from "../components/unranked-jobs";

test("unranked jobs show honest uncertainty and direct repair links", () => {
 const html=renderToStaticMarkup(React.createElement(UnrankedJobs,{ids:["job /1"], labels:{"job /1":"合成岗位"}}));
 assert.match(html,/未出现在本次排序/);
 assert.match(html,/不等于系统确认你不具备能力/);
 assert.match(html,/\/jobs\/job%20%2F1/);
 assert.match(html,/合成岗位/);
 assert.equal(renderToStaticMarkup(React.createElement(UnrankedJobs,{ids:[]})), "");
});
