import assert from "node:assert/strict";
import test from "node:test";

import {selectFeedbackDisplayItems} from "../lib/match-report";

type Item = {
  report: {
    reportId: string;
  };
};

function items(count: number): Item[] {
  return Array.from({length: count}, (_, index) => ({
    report: {reportId: `report_${index + 1}`},
  }));
}

test("keeps the next pending feedback report visible beyond the initial blocked cap", () => {
  const blocked = items(8);

  const visible = selectFeedbackDisplayItems(blocked, "report_6", 5);

  assert.deepEqual(
    visible.map((item) => item.report.reportId),
    ["report_1", "report_2", "report_3", "report_4", "report_5", "report_6"],
  );
});

test("does not duplicate the next pending report when it is already visible", () => {
  const blocked = items(8);

  const visible = selectFeedbackDisplayItems(blocked, "report_3", 5);

  assert.deepEqual(
    visible.map((item) => item.report.reportId),
    ["report_1", "report_2", "report_3", "report_4", "report_5"],
  );
});

test("keeps the normal capped display when no pending feedback report is known", () => {
  const blocked = items(8);

  const visible = selectFeedbackDisplayItems(blocked, null, 5);

  assert.deepEqual(
    visible.map((item) => item.report.reportId),
    ["report_1", "report_2", "report_3", "report_4", "report_5"],
  );
});

test("preserves a focused report outside the cap together with the next pending report", () => {
  const blocked = items(9);

  const visible = selectFeedbackDisplayItems(blocked, "report_6", 5, ["report_9"]);

  assert.deepEqual(
    visible.map((item) => item.report.reportId),
    ["report_1", "report_2", "report_3", "report_4", "report_5", "report_6", "report_9"],
  );
});
