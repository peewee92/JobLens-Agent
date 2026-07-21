const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const context = { console, __BOSS_JOB_FILTER_TEST__: true };
context.globalThis = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync(require.resolve('../lib.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(require.resolve('../content.js'), 'utf8'), context);
const { findAreaInText } = context.BossAiContentInternals;

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
