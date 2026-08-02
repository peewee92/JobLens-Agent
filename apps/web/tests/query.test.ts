import assert from "node:assert/strict";
import test from "node:test";

import {buildJobQuery, jobsHref, parseJobFilters} from "@/lib/query";

test("parseJobFilters sanitizes unsupported values", () => {
  const filters = parseJobFilters({
    q: ["Agent", "ignored"],
    city: " 武汉 ",
    minSalaryK: "-5",
    remoteStatus: "maybe",
    source: " BOSS ",
    sort: "unknown",
    limit: "999",
    offset: "-1",
  });

  assert.deepEqual(filters, {
    q: "Agent",
    city: "武汉",
    minSalaryK: "",
    remoteStatus: "",
    source: "boss",
    sort: "latest",
    limit: 100,
    offset: 0,
  });
});

test("buildJobQuery emits only stable backend parameters", () => {
  const filters = parseJobFilters({
    q: "RAG",
    city: "武汉",
    minSalaryK: "20",
    remoteStatus: "confirmed",
    source: "boss",
    sort: "salaryDesc",
    limit: "10",
    offset: "20",
  });

  assert.equal(
    buildJobQuery(filters).toString(),
    "q=RAG&city=%E6%AD%A6%E6%B1%89&minSalaryK=20&remoteStatus=confirmed&source=boss&sort=salaryDesc&limit=10&offset=20",
  );
  assert.equal(jobsHref(filters, 30).endsWith("offset=30"), true);
});

test("default filters produce a clean /jobs URL", () => {
  const filters = parseJobFilters({});
  assert.equal(buildJobQuery(filters).toString(), "");
  assert.equal(jobsHref(filters), "/jobs");
});
