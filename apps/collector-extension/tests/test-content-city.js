const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const context = { console, __BOSS_JOB_FILTER_TEST__: true };
context.globalThis = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync(require.resolve('../lib.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(require.resolve('../content.js'), 'utf8'), context);
const {
  findAreaInText,
  getElementText,
  chooseDescriptionCandidate
} = context.BossAiContentInternals;

const duplicateTextElement = {
  innerText: 'AI Agent 工程师',
  textContent: 'AI Agent 工程师',
  getAttribute: () => null
};
assert.strictEqual(getElementText(duplicateTextElement), 'AI Agent 工程师');

const trustedJd = [
  '岗位职责：',
  '1. 负责企业级 AI Agent 应用设计、开发和上线。',
  '2. 建设工具调用、RAG、评测和可观测工作流。',
  '任职要求：',
  '1. 熟悉 Python、FastAPI 和大模型 API。',
  '2. 具备三年以上开发、测试和真实项目交付经验。',
  '3. 能够分析 Trace 并持续优化系统可靠性。'
].join('\n');
const noisyBroadText = [
  '下载App, 不错过Boss每一条消息',
  '职位描述',
  trustedJd,
  '认证资质 人力资源服务许可证',
  '竞争力分析',
  'BOSS 安全提示',
  '更多职位 看过该职位的人还看了'
].join('\n');
const elementsBySelector = new Map([
  ['.job-sec-text', [{ innerText: trustedJd, textContent: trustedJd }]],
  ['[class*="job-detail"]', [{ innerText: noisyBroadText, textContent: noisyBroadText }]]
]);
context.document = {
  querySelectorAll(selector) {
    return elementsBySelector.get(selector) || [];
  }
};
const selected = chooseDescriptionCandidate();
assert.strictEqual(selected.descriptionSource, 'selector:.job-sec-text');
assert.strictEqual(selected.descriptionSelectorTrust, 'trusted');
assert.strictEqual(selected.description, trustedJd);
assert.ok(!selected.description.includes('BOSS 安全提示'));

assert.strictEqual(findAreaInText('AI Agent工程师 20-30K 成都·武侯区·金融城', {}, {
  scope: '成都', scopeType: 'city', cityName: '成都'
}), '成都·武侯区·金融城');
assert.strictEqual(findAreaInText('大模型应用开发 15-25K 武汉·洪山区·光谷', {}, {
  scope: '武汉', scopeType: 'city', cityName: '武汉'
}), '武汉·洪山区·光谷');
assert.strictEqual(findAreaInText('AI应用工程师 20-40K 深圳·南山区', {}, {
  scope: '深圳', scopeType: 'city', cityName: '深圳'
}), '深圳·南山区');

console.log('General city area fallback tests passed.');
