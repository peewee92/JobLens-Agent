import {strict as assert} from "node:assert";
import test from "node:test";
import {jobDocumentRoute, openSavedJobDocument, requirementsConfirmedHref, savedModelExtractionHref, savedModelReportHref} from "../lib/authorized-model-results";

test("the saved receipt opens the exact report and retains comparison context", () => {
  assert.equal(
    savedModelReportHref("/jobs/job_a?scopeJobId=job_a&scopeJobId=job_b&reportId=old&returnThreadId=t#old", "saved/1"),
    "/jobs/job_a?scopeJobId=job_a&scopeJobId=job_b&reportId=saved%2F1&returnThreadId=t#job-match-report",
  );
  assert.equal(savedModelReportHref("/jobs/job_a", "new"), "/jobs/job_a?reportId=new#job-match-report");
});

test("extraction completion returns to requirement review and preserves other page context", () => {
  assert.equal(
    savedModelExtractionHref("/jobs/job_a?scopeJobId=job_a&scopeJobId=job_b&reportId=prior#job-match", "extract-1"),
    "/jobs/job_a?scopeJobId=job_a&scopeJobId=job_b&reportId=prior&reviewExtraction=extract-1#job-requirements",
  );
});

test("confirmation opens fresh matching inputs without repeating any model action", () => {
  const href = requirementsConfirmedHref("/jobs/job_a?scopeJobId=job_a&scopeJobId=job_b", "r1");
  assert.equal(href, "/jobs/job_a?scopeJobId=job_a&scopeJobId=job_b&confirmedRequirements=r1#job-match-report");
  const visited: string[] = [];
  const location = {pathname: "/jobs/job_a", search: "?reviewExtraction=r1", hash: "#job-requirements",
    replace(value: string) { visited.push(value); }, reload() { visited.push("reload"); }};
  openSavedJobDocument(location, href, jobDocumentRoute(location));
  assert.deepEqual(visited, [href]);
  location.search = "?scopeJobId=job_a&scopeJobId=job_b&confirmedRequirements=r1";
  location.hash = "#job-match-report";
  openSavedJobDocument(location, href, jobDocumentRoute(location));
  assert.deepEqual(visited, [href, "reload"]);
});


test("a completion arriving after a move to a different job never steals navigation", () => {
  const destination = savedModelReportHref("/jobs/job_a?scopeJobId=job_a", "report");
  const visited: string[] = [];
  const location = {pathname: "/jobs/job_a", search: "?scopeJobId=job_a", hash: "#job-match-report",
    replace(value: string) { visited.push(value); }, reload() { visited.push("reload"); }};
  const started = jobDocumentRoute(location);
  location.pathname = "/jobs/job_b";
  openSavedJobDocument(location, destination, started);
  location.pathname = "/jobs/job_a";
  location.search = "?scopeJobId=job_b&scopeJobId=job_a";
  openSavedJobDocument(location, destination, started);
  assert.deepEqual(visited, []);
});
