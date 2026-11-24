const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');

const source = name => fs.readFileSync(require.resolve('../' + name), 'utf8');
const jobUrl = 'https://www.zhipin.com/job_detail/testAB12.html';
const anotherUrl = 'https://www.zhipin.com/job_detail/testCD34.html';
const jd = [
  '岗位职责：',
  '1. 负责订单系统的开发、测试与维护，建设可复用的服务接口，及时定位并修复线上业务问题。',
  '2. 参与跨团队需求评审和技术方案讨论，设计自动化测试，优化关键接口的响应时间，维护上线文档。',
  '任职要求：',
  '1. 熟悉 Python 和关系数据库，掌握单元测试和日志排查方法，具备三年以上后端相关开发经验。',
  '2. 能够独立交付迭代需求，具备良好的沟通和文档编写能力，有任务调度或数据处理项目经验者优先。',
  '3. 优先考虑具备性能分析经验的候选人。'
].join('\n');

function element(innerText = '', { hidden = false, classes = [], children = {}, href, clamp } = {}) {
  return {
    href, innerText, clamp,
    clientHeight: 20,
    scrollHeight: clamp ? 50 : 20,
    getClientRects: () => hidden ? [] : [{}],
    closest: selector => classes.find(name => selector.includes(name)) || null,
    querySelectorAll: selector => children[selector] || []
  };
}

const descSelector = '.job-detail-section .job-sec-text, .job-detail .job-sec-text';
const recommendationSelector = '.recommend-job, .job-recommend, .job-card-wrapper, .job-card-box, .similar-job, aside';

function capture({
  description = jd, fold, crop, recommendations, nestedRecommendations, duplicate, missing, noCompany,
  canonical = jobUrl, href = jobUrl + '?sessionId=local-test#page', expectedUrl = jobUrl,
  title = '示例工程师 - BOSS直聘', dialog = '', inProgress = false, area = '深圳', salary = '20-30K'
} = {}) {
  const controls = 'a, button, [role="button"], .show-more, .expand-btn, .text-more';
  const desc = element(crop ? description.repeat(210) : description, {
    classes: fold === 'class' ? ['.job-sec-text.collapsed'] : [],
    clamp: fold === 'clamp' ? '5' : null,
    children: {
      [controls]: fold === 'button' ? [element('查看完整岗位描述')] : [],
      [recommendationSelector]: nestedRecommendations ? [element('推荐职位')] : []
    }
  });
  const banner = element('', { children: {
    h1: [element('示例工程师')],
    '.job-info .text-city, .job-info .job-area, .job-info .job-location': [element(area)],
    '.name .salary, .job-salary, .salary': [element(salary)]
  } });
  const query = {
    '.job-banner': [banner],
    [descSelector]: [
      ...(missing ? [] : [desc]),
      ...(recommendations ? [element('别的岗位', { classes: ['.recommend-job'] }), element('隐藏正文', { hidden: true })] : []),
      ...(duplicate ? [element('也像主详情的正文')] : [])
    ],
    'link[rel="canonical"]': canonical ? [element('', { href: canonical })] : [],
    '[role="dialog"], .boss-popup__title': dialog ? [element(dialog)] : []
  };
  const context = vm.createContext({
    URL, __BOSS_JOB_FILTER_TEST__: true,
    location: new URL(href),
    document: {
      readyState: inProgress ? 'loading' : 'complete',
      title,
      get body() { throw new Error('current job capture must not access document.body'); },
      querySelectorAll: selector => query[selector] || (selector.startsWith('.sider-company') && !noCompany
        ? [element('示例公司'), element('另一家公司', { classes: ['.recommend-job'] })] : [])
    },
    getComputedStyle: node => ({ visibility: 'visible', webkitLineClamp: node.clamp })
  });
  for (const script of ['lib.js', 'content.js']) vm.runInContext(source(script), context);
  return context.BossAiContentInternals.captureCurrentJob(expectedUrl);
}

test('reads only the trusted visible job, excludes recommendations, and strips the URL query/hash', () => {
  const { status, job } = capture({ recommendations: true });
  assert.equal(status, 'preview');
  assert.equal(job.url, jobUrl);
  assert.equal(job.description, jd);
  assert.equal(job.title, '示例工程师');
  assert.equal(job.company, '示例公司');
  assert.deepEqual([job.area, job.salary, job.salaryMinK, job.salaryMaxK], ['深圳', '20-30K', 20, 30]);
  assert.equal(job.descriptionQuality, 'full_jd');
  assert.equal(job.requirementReviewEligible, true);
  for (const key of ['detailText', 'rawText', 'recruiterActive']) assert.equal(key in job, false);
  assert.equal(capture({ description: jd + '\nBOSS 安全提示\n尾部信息' }).job.description, jd);
  for (const salary of ['20-\uE8000K', '30-20K', '']) {
    const optional = capture({ area: '', salary }).job;
    assert.deepEqual([optional.area, optional.salary, optional.salaryMinK, optional.salaryMaxK], [null, '', null, null]);
    assert.equal(optional.requirementReviewEligible, true);
  }
});

test('rejects conflicting identity, recommendation mixed into the main block, unsupported routes, and verification', () => {
  assert.equal(capture({ href: anotherUrl }).status, 'changed');
  assert.equal(capture({ canonical: anotherUrl }).status, 'conflict');
  assert.equal(capture({ canonical: 'https://evil.invalid/job_detail/testAB12.html' }).status, 'conflict');
  assert.equal(capture({ duplicate: true }).status, 'conflict');
  assert.equal(capture({ nestedRecommendations: true }).status, 'conflict');
  assert.equal(capture({ noCompany: true }).status, 'unready');
  assert.equal(capture({ inProgress: true }).status, 'unready');
  assert.equal(capture({ href: 'https://www.zhipin.com/web/geek/jobs', expectedUrl: '' }).status, 'unsupported');
  assert.equal(capture({ href: 'https://host.invalid/job_detail/testAB12.html' }).status, 'changed');
  assert.equal(capture({ title: '安全验证' }).status, 'blocked');
  assert.equal(capture({ dialog: '登录后查看职位' }).status, 'blocked');
  assert.equal(capture({ href: 'https://www.zhipin.com/web/user/login', expectedUrl: '' }).status, 'blocked');
});

test('visible folding and local clipping never pass; content length alone is not evidence of truncation', () => {
  const complete400 = (jd + '\n' + '有大型任务调度项目经验者优先。'.repeat(15)).slice(0, 399) + '。';
  assert.equal(complete400.length, 400);
  assert.equal(capture({ description: complete400 }).job.descriptionQuality, 'full_jd');
  for (const fold of ['button', 'clamp', 'class']) {
    const { job } = capture({ description: complete400, fold });
    assert.equal(job.descriptionQuality, 'partial_jd');
    assert.equal(job.requirementReviewEligible, false);
    assert.ok(job.requirementReviewIneligibilityReasons.includes('visible_description_folded'));
  }
  const limited = capture({ crop: true }).job;
  assert.equal(limited.description.length, 30_000);
  assert.equal(limited.requirementReviewEligible, false);
  assert.ok(limited.requirementReviewIneligibilityReasons.includes('description_capture_limit'));
  assert.equal(capture({ missing: true }).job.descriptionQuality, 'unavailable');
  assert.equal(capture({ description: '熟悉 Python，三年以上开发经验。' }).job.requirementReviewEligible, false);
});

if (process.env.JOBLENS_PRIVATE_JD_FIXTURE) {
  test('replays three private short/long pairs with simulated fold state, never logs the JD', () => {
    const { samples } = JSON.parse(fs.readFileSync(process.env.JOBLENS_PRIVATE_JD_FIXTURE, 'utf8'));
    const pairs = samples.filter(sample => sample.sourceReadiness === 'truncated');
    assert.equal(pairs.length, 3);
    for (const pair of pairs) {
      assert.ok(pair.referenceDescription.startsWith(pair.description), pair.id);
      assert.equal(capture({ description: pair.description, fold: 'button' }).job.requirementReviewEligible, false, pair.id);
      assert.equal(capture({ description: pair.referenceDescription }).job.requirementReviewEligible, true, pair.id);
    }
  });
}

function popup({ tab = { id: 4, url: jobUrl }, job = capture().job, response, stored = {} } = {}) {
  const elements = {};
  const posts = [];
  const messages = [];
  const opened = [];
  const downloads = [];
  const state = { tab, result: { status: 'preview', job }, response, onMessage: null };
  const db = { lastRun: { untouched: true }, ...stored };
  const get = id => elements[id] ||= {
    value: id === 'quickTarget' ? 'local' : '',
    addEventListener(event, handler) { this[event] = handler; }
  };
  const context = vm.createContext({
    URL, AbortSignal,
    document: { getElementById: get },
    chrome: {
      tabs: {
        query: async () => [state.tab],
        sendMessage: async (tabId, message, options) => {
          messages.push([tabId, message, options]);
          state.onMessage?.();
          return state.result;
        },
        create: async ({ url }) => { opened.push(url); }
      },
      storage: { local: {
        get: async () => db,
        set: async data => Object.assign(db, data),
        remove: async key => delete db[key]
      } }
    },
    fetch: async (url, options) => {
      posts.push({ url, options });
      if (state.response instanceof Error) throw state.response;
      return {
        ok: true,
        json: async () => state.response || { importId: 'imp_test', received: 1, created: 1, updated: 0, skipped: 0, errors: [] }
      };
    },
    downloadData: async (...args) => { downloads.push(args); }
  });
  for (const script of ['lib.js', 'joblens-sync.js', 'quick-save.js']) vm.runInContext(source(script), context);
  return { get, click: id => get(id).click(), posts, messages, opened, downloads, state, db,
    ready: new Promise(resolve => setImmediate(resolve)) };
}

test('explicit confirmation posts a single Collector report and opens the matching audit', async () => {
  const p = popup();
  await p.ready;
  await p.click('quickSync');
  await p.click('quickCapture');
  assert.equal(p.posts.length, 0);
  assert.equal(p.get('quickActions').hidden, false);
  assert.match(p.get('quickStatus').textContent, /尚未同步/);
  assert.equal(p.get('quickDescription').value, jd);
  await Promise.all([p.click('quickSync'), p.click('quickSync')]);
  assert.equal(p.posts.length, 1);
  assert.deepEqual(p.messages.map(([tabId, message, options]) => [tabId, message.expectedUrl, options.frameId]),
    [[4, jobUrl, 0], [4, jobUrl, 0]]);
  const { url, options } = p.posts[0];
  assert.equal(url, 'http://127.0.0.1:8102/api/v1/job-imports');
  assert.equal(options.method, 'POST');
  assert.equal(options.redirect, 'error');
  assert.equal(options.credentials, 'omit');
  assert.ok(options.signal instanceof AbortSignal);
  const report = JSON.parse(options.body);
  assert.equal(report.version, '1.6.0');
  assert.equal(report.jobs.length, 1);
  assert.equal(report.jobs[0].description, jd);
  assert.deepEqual(report.candidates, []);
  assert.deepEqual(p.db.lastRun, { untouched: true });
  await p.click('quickOpenImport');
  assert.deepEqual(p.opened, ['http://127.0.0.1:3102/imports/imp_test']);
});

test('mobile and desktop search pages explain where quick save works without importing', async () => {
  const p = popup({ tab: { id: 4, url: 'https://m.zhipin.com/web/geek/jobs?city=101200100' } });
  await p.ready;
  await p.click('quickCapture');
  assert.match(p.get('quickStatus').textContent, /桌面版.*www\.zhipin\.com.*独立职位详情/);
  assert.equal(p.messages.length, 0);
  assert.equal(p.get('quickPreview').hidden, true);
  p.state.tab = { id: 4, url: 'https://www.zhipin.com/web/geek/jobs' };
  p.state.result = { status: 'unsupported' };
  await p.click('quickCapture');
  assert.match(p.get('quickStatus').textContent, /列表.*右侧预览/);
  assert.equal(p.get('quickActions').hidden, true);
  assert.equal(p.posts.length, 0);
});

test('changed tabs, pending navigations, revised content, and blocked previews never post', async () => {
  const p = popup();
  await p.ready;
  await p.click('quickCapture');
  p.state.tab = { id: 8, url: jobUrl };
  await p.click('quickSync');
  assert.match(p.get('quickStatus').textContent, /岗位已切换/);
  p.state.tab = { id: 4, url: jobUrl, pendingUrl: anotherUrl };
  await p.click('quickSync');
  assert.match(p.get('quickStatus').textContent, /岗位已切换/);
  p.state.tab = { id: 4, url: jobUrl };
  p.state.onMessage = () => { p.state.tab = { id: 4, url: anotherUrl }; };
  await p.click('quickSync');
  assert.match(p.get('quickStatus').textContent, /岗位已切换/);
  p.state.onMessage = null;
  p.state.tab = { id: 4, url: jobUrl };
  p.state.result = { status: 'preview', job: capture({ description: jd + '\n有测试经验者优先。' }).job };
  await p.click('quickSync');
  assert.match(p.get('quickStatus').textContent, /内容已变化/);
  p.state.result = { status: 'preview', job: capture({ fold: 'button' }).job };
  await p.click('quickCapture');
  assert.match(p.get('quickQuality').textContent, /仍折叠/);
  assert.equal(p.get('quickActions').hidden, true);
  await p.click('quickSync');
  await p.click('quickDownload');
  p.state.result = { status: 'blocked' };
  await p.click('quickCapture');
  assert.match(p.get('quickStatus').textContent, /手动处理/);
  assert.equal(p.get('quickPreview').hidden, true);
  assert.equal(p.posts.length, 0);
  assert.equal(p.downloads.length, 0);
});

test('unconfirmed sync retains the draft and compatibility JSON; explicit retry can use the development target', async () => {
  const p = popup({ response: new Error('service unavailable') });
  await p.ready;
  await p.click('quickCapture');
  await p.click('quickSync');
  assert.match(p.get('quickStatus').textContent, /同步未确认/);
  assert.equal(p.get('quickOpenImport').hidden, true);
  const reopened = popup({ stored: { quickSaveDraft: p.db.quickSaveDraft } });
  await reopened.ready;
  assert.equal(reopened.posts.length, 0);
  assert.equal(reopened.get('quickDescription').value, jd);
  await reopened.click('quickDownload');
  assert.equal(reopened.downloads[0][0].startsWith('boss-job-filter-quick-v1.6.0-'), true);
  assert.deepEqual(JSON.parse(reopened.downloads[0][2]), JSON.parse(p.posts[0].options.body));
  assert.equal(reopened.posts.length, 0);

  p.get('quickTarget').value = 'not-local';
  await p.click('quickSync');
  assert.equal(p.posts.length, 1);
  p.get('quickTarget').value = 'development';
  p.state.response = { importId: 'https://other.invalid/', received: 1, created: 1, updated: 0, skipped: 0, errors: [] };
  await p.click('quickSync');
  assert.equal(p.get('quickOpenImport').hidden, true);
  p.state.response = { importId: 'imp_test', received: 1, created: 0, updated: 0, skipped: 1, errors: ['error'] };
  await p.click('quickSync');
  assert.equal(p.get('quickOpenImport').hidden, true);
  p.state.response.errors = [];
  await p.click('quickSync');
  assert.match(p.get('quickStatus').textContent, /跳过 1/);
  assert.equal(p.posts.at(-1).url, 'http://127.0.0.1:8000/api/v1/job-imports');
  await p.click('quickOpenImport');
  assert.deepEqual(p.opened, ['http://127.0.0.1:3000/imports/imp_test']);
});
