import test from 'node:test';
import assert from 'node:assert/strict';
import {gapScope, gapScopeHref, withGapReturn} from '../lib/gap-scope';
test('gap recovery preserves the exact cohort, hash and local return route', () => {
  const ids = gapScope(['job_2', 'job_1', 'job_2']);
  assert.deepEqual(ids, ['job_2', 'job_1']);
  const detail = withGapReturn('/jobs/job_2#job-requirements', ids);
  assert.equal(detail, '/jobs/job_2?gapJobId=job_2&gapJobId=job_1#job-requirements');
  assert.equal(gapScopeHref(ids), '/gaps?from=agent&jobId=job_2&jobId=job_1');
});
test('gap recovery rejects untrusted or oversized cohorts rather than selecting other jobs', () => {
  assert.deepEqual(gapScope('https://outside.example'), []);
  assert.deepEqual(gapScope(Array.from({length:51}, (_, n) => `job_${n}`)), []);
});
