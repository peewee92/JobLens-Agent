const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const context = { console, JSON, Error };
context.globalThis = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync(require.resolve('../joblens-sync.js'), 'utf8'), context);
const sync = context.JobLensSync;

assert.strictEqual(sync.DEFAULT_ENDPOINT, 'http://127.0.0.1:8000/api/v1/job-imports');

const report = { version: '1.4.6', jobs: [{ title: 'AI Engineer' }] };
assert.deepStrictEqual(JSON.parse(JSON.stringify(sync.parseReport({ report }))), report);
assert.deepStrictEqual(
  JSON.parse(JSON.stringify(sync.parseReport({ json: JSON.stringify(report) }))),
  report
);
assert.throws(() => sync.parseReport({}), /还没有可同步的完整报告/);

(async () => {
  let request = null;
  const result = await sync.syncReport(report, {
    fetchImpl: async (url, options) => {
      request = { url, options };
      return {
        ok: true,
        status: 201,
        async json() {
          return { created: 1, updated: 2, skipped: 3, errors: [] };
        }
      };
    }
  });

  assert.strictEqual(request.url, sync.DEFAULT_ENDPOINT);
  assert.strictEqual(request.options.method, 'POST');
  assert.strictEqual(request.options.headers['Content-Type'], 'application/json');
  assert.deepStrictEqual(JSON.parse(request.options.body), report);
  assert.strictEqual(result.created, 1);
  assert.strictEqual(
    sync.formatSyncResult(result),
    '已同步到 JobLens：新增 1，更新 2，跳过 3。'
  );

  await assert.rejects(
    () => sync.syncReport(report, {
      fetchImpl: async () => ({
        ok: false,
        status: 422,
        async json() { return { detail: { message: '报告格式不正确' } }; }
      })
    }),
    /报告格式不正确/
  );

  console.log('joblens sync tests passed');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
