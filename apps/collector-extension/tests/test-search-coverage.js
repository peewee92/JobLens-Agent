const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');

const context = vm.createContext({ URL, URLSearchParams, __BOSS_JOB_FILTER_TEST__: true });
for (const file of ['lib.js', 'runner.js', 'content.js']) {
  vm.runInContext(fs.readFileSync(require.resolve('../' + file), 'utf8'), context, { filename: file });
}
const { recordSearchPage, buildSearchCoverage, collectSearchPages } = context.BossAiRunnerInternals;
const { extractList } = context.BossAiContentInternals;
const url = id => `https://www.zhipin.com/job_detail/example-${id}.html`;
const scope = { scope: '武汉', scopeType: 'city', cityName: '武汉', cityCode: '101200100', searchQuery: 'AI' };
const page = (n, ids, extra = {}) => ({ observedPage: n, pageState: 'read', jobs: ids.map(id => ({ url: url(id) })), ...extra });
const history = () => ({ seen: new Set(), previous: null, noNewReads: 0 });

test('checks actual link sets; one repeated page does not skip page 3', () => {
  const query = history();
  const city = new Set();
  const take = (n, result) => recordSearchPage(result, { ...scope, page: n }, query, city);
  assert.equal(take(1, page(1, ['a', 'b'])).newWithinQuery, 2);
  const repeated = take(2, page(2, ['b', 'a']));
  assert.equal(repeated.status, 'repeated');
  assert.equal(repeated.sameAsPreviousPage, true);
  assert.equal(repeated.noNewReads, 1);
  const third = take(3, page(3, ['b', 'c']));
  assert.equal(third.status, 'read');
  assert.equal(third.newWithinQuery, 1);
  assert.equal(third.newWithinScope, 1);
  assert.equal(third.noNewReads, 0);
  assert.equal(take(4, page(4, ['a'])).sameAsPreviousPage, false);
  const nextQuery = recordSearchPage(page(1, ['a', 'd']), { ...scope, page: 1 }, history(), city);
  assert.equal(nextQuery.newWithinQuery, 2);
  assert.equal(nextQuery.newWithinScope, 1);
});

test('never treats empty, failed, blocked or mismatched pages as duplicates or as successful card reads', () => {
  const query = history();
  const city = new Set();
  recordSearchPage(page(1, ['a']), { ...scope, page: 1 }, query, city);
  for (const [result, expected] of [
    [page(1, ['a']), 'unready'],
    [{ jobs: [] }, 'unready'],
    [{ error: 'fixture error', jobs: [{ url: url('bad') }] }, 'read_failed'],
    [{ blocked: true, jobs: [{ url: url('bad') }] }, 'blocked'],
    [{ pageState: 'no_results', jobs: [] }, 'no_results']
  ]) {
    const row = recordSearchPage(result, { ...scope, page: 2 }, query, city);
    assert.equal(row.status, expected);
    assert.equal(row.cards, 0);
    assert.equal(row.sameAsPreviousPage, false);
    assert.equal(row.noNewReads, 0);
  }
  assert.equal(city.size, 1);
  const end = recordSearchPage(page(3, ['b'], { lastPage: true }), { ...scope, page: 3 }, query, city);
  assert.equal(end.status, 'last_page');
  assert.equal(end.newWithinScope, 1);
});

test('coverage separates requested and read pages from deduped candidates and scoped filter results', () => {
  const remote = { scope: '全国远程', scopeType: 'remote' };
  const pages = [
    { ...scope, status: 'read', cards: 3, newWithinScope: 3 },
    { ...scope, status: 'unready', cards: 0, newWithinScope: 0 },
    { ...scope, status: 'no_results', cards: 0, newWithinScope: 0 },
    { ...remote, status: 'blocked', cards: 0, newWithinScope: 0 },
    { ...remote, status: 'last_page', cards: 1, newWithinScope: 1 }
  ];
  const coverage = buildSearchCoverage(pages, [
    { job: { ...scope, url: url('a') }, keep: true },
    { job: { ...scope, url: url('b') }, keep: false, reason: '薪资低于阈值' },
    { job: { ...remote, url: url('a') }, keep: true }
  ]);
  assert.deepEqual(Array.from(coverage, row => [
    row.scope, row.requestedPages, row.readPages, row.rawHits, row.uniqueCards, row.kept
  ]), [['武汉', 3, 2, 3, 3, 1], ['全国远程', 2, 1, 1, 1, 1]]);
  assert.equal(coverage[0].rejectedReasons['薪资低于阈值'], 1);
});

function element(text = '', options = {}) {
  return {
    innerText: text,
    href: options.href,
    getClientRects: () => options.hidden ? [] : [{}],
    getAttribute: key => options.attributes?.[key] ?? null,
    querySelector: key => options.one?.[key] ?? null,
    querySelectorAll: key => options.many?.[key] ?? [],
    closest: key => options.closest?.(key) ?? null,
    contains: node => options.contains?.includes(node) ?? false
  };
}

test('content reads the existing main list only and distinguishes explicit empty and unread pages', () => {
  const anchorSelector = 'a[href*="/job_detail/"]';
  const card = element('后端工程师 20-30K', { one: { '.job-name': element('后端工程师'), '.company-name': element('示例公司') } });
  const normal = element('后端工程师', { href: url('a') + '?lid=tracking', closest: selector => selector.includes('.job-card-wrapper') ? card : null });
  const side = element('推荐岗位', { href: url('side') });
  const hidden = element('隐藏岗位', { href: url('hidden'), hidden: true });
  const recommended = element('推荐岗位', { href: url('nested'), closest: selector =>
    selector.includes('.recommend-job') || selector.includes('.job-card-wrapper') ? card : null });
  const pager = element('2', { closest: selector => selector === 'nav' ? nav : null });
  const nav = element('', { one: { '[rel~="next"]': element('下一页', { attributes: { 'aria-disabled': 'true' } }) } });
  const validList = element('', {
    contains: [card], many: { [anchorSelector]: [normal, hidden, recommended], 'nav [aria-current="page"]': [pager] }
  });
  const setPage = (list, path = '/web/geek/jobs?query=AI&city=101200100&page=1', title = '') => {
    context.location = new URL('https://www.zhipin.com' + path);
    context.getComputedStyle = () => ({ visibility: 'visible' });
    context.document = {
      title, readyState: 'complete', body: element(),
      querySelectorAll: key => key === '.job-list-box' ? list : key === anchorSelector ? [side] : []
    };
  };
  const meta = { ...scope, page: 1 };
  setPage([validList]);
  const result = extractList(meta);
  assert.deepEqual(Array.from(result.jobs, j => j.url), [url('a')]);
  assert.equal(result.observedPage, 2);
  assert.equal(result.lastPage, true);
  setPage([], undefined, '请完成安全验证');
  assert.equal(extractList(meta).blocked, true);
  setPage([]);
  assert.equal(extractList(meta).pageState, 'unready');
  setPage([element('暂无相关职位')]);
  assert.equal(extractList(meta).pageState, 'no_results');
  setPage([validList], '/web/geek/jobs?query=AI&city=101280600&page=1');
  assert.equal(extractList(meta).pageState, 'unready');
});


test('batch loop reaches page 3 on overlap or unread page and stops on a confirmed last page', async () => {
  const elements = new Map();
  const requested = [];
  const listeners = new Set();
  context.setTimeout = (callback, ms) => { if (ms !== 70_000) queueMicrotask(callback); };
  context.clearTimeout = () => {};
  context.document = { getElementById(id) {
    if (!elements.has(id)) elements.set(id, { textContent: '' });
    return elements.get(id);
  } };
  context.chrome = { tabs: {
    create: async () => ({ id: 7 }),
    onUpdated: {
      addListener: listener => listeners.add(listener),
      removeListener: listener => listeners.delete(listener)
    },
    async update(id, { url }) {
      if (url) {
        const params = new URL(url).searchParams;
        requested.push([params.get('query'), Number(params.get('page'))]);
        for (const listener of listeners) listener(id, { status: 'complete' });
      }
    },
    async sendMessage(_id, { meta }) {
      if (meta.searchKeyword === 'end') return page(1, ['a'], { lastPage: true });
      if (meta.searchKeyword === 'unready' && meta.page === 2) return { jobs: [], pageState: 'unready' };
      return page(meta.page, [meta.page === 3 ? 'new' : 'a']);
    }
  } };
  await collectSearchPages({ scopes: { wuhan: true }, keywords: ['overlap', 'unready', 'end'], pagesPerQuery: 3, smartStop: true });
  assert.deepEqual(requested, [
    ['overlap', 1], ['overlap', 2], ['overlap', 3], ['unready', 1], ['unready', 2], ['unready', 3], ['end', 1]
  ]);
  const log = elements.get('log').textContent;
  assert.match(log, /链接集合与上一页相同/);
  assert.match(log, /页面未就绪或无法确认/);
  assert.match(log, /站点标记末页/);
});
