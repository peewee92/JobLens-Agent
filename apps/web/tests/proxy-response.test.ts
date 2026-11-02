import test from 'node:test';
import assert from 'node:assert/strict';
import {forwardBackendResponse} from '../lib/proxy-response';
import {readExecutionResponse} from '../lib/analysis-execution';

test('decoded backend payload does not retain compressed wire headers', async () => {
  const upstream = new Response(JSON.stringify({items: [{workspaceId: 'synthetic'}]}), {headers: {
    'content-type':'application/json', 'content-encoding':'gzip', 'content-length':'19', 'transfer-encoding':'chunked', 'cache-control':'no-store',
  }});
  const forwarded = forwardBackendResponse(upstream);
  assert.equal(forwarded.headers.get('content-encoding'), null);
  assert.equal(forwarded.headers.get('content-length'), null);
  assert.equal(forwarded.headers.get('transfer-encoding'), null);
  assert.equal(forwarded.headers.get('cache-control'), 'no-store');
  assert.deepEqual(await forwarded.json(), {items:[{workspaceId:'synthetic'}]});
});
test('empty upstream result stays empty', () => {
  assert.equal(forwardBackendResponse(new Response(null, {status:204})).body, null);
});
test('gateway HTML is an uncertain result, not a raw parser exception', async () => {
  await assert.rejects(readExecutionResponse(new Response('<!DOCTYPE html>gateway unavailable', {status:502})), /请先查看已保存工作区.*重试原请求/);
});
