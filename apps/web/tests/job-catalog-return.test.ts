import assert from "node:assert/strict";
import test from "node:test";
import {jobCatalogPath, jobCatalogRowId, withJobCatalogReturn} from "../lib/job-catalog-return";

test("a detail return keeps the known catalog search, paging and sort controls", () => {
  const returnPath = jobCatalogPath("/jobs?sort=salaryDesc&offset=20&q=Python&unrelated=1");
  assert.equal(returnPath, "/jobs?q=Python&sort=salaryDesc&offset=20");
  const href = new URL(withJobCatalogReturn("/jobs/job_1?reportId=older", returnPath), "https://joblens.example");
  assert.equal(href.searchParams.get("returnJobs"), returnPath);
  assert.equal(href.searchParams.get("reportId"), "older");
  assert.equal(jobCatalogRowId("job_1"), "saved-job-job_1");
});

test("a detail return cannot leave the catalog or set an arbitrary fragment", () => {
  for (const value of ["//example.com/jobs", "https://example.com/jobs", "/jobs/../connect", "/jobs#anything", ["/jobs"]]) {
    assert.equal(jobCatalogPath(value), null);
  }
  assert.equal(jobCatalogPath("/jobs"), "/jobs");
});
