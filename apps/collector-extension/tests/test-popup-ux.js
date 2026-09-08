const fs = require('fs');
const assert = require('assert');

const html = fs.readFileSync(require.resolve('../popup.html'), 'utf8');
const js = fs.readFileSync(require.resolve('../popup.js'), 'utf8');

for (const copy of [
  '最低月薪门槛（K/月）',
  '怎么判断薪资达标',
  '每个关键词最多搜几页',
  '远程岗位怎么确认',
  '哪些岗位要打开详情页',
  '最多打开多少个详情页',
  '岗位与搜索词最低匹配分',
  '什么时候提前停止翻页',
  '当前实际覆盖范围',
  '结果可能偏少的原因',
  '高级设置（一般不用改）'
]) {
  assert.ok(html.includes(copy), `popup should explain ${copy}`);
}

assert.ok(html.includes('不会包含其他城市的线下岗位'), 'remote scope copy should explain nationwide remote is not nationwide onsite search');
assert.ok(html.includes('data-tooltip='), 'advanced fields should expose hover/focus help');
assert.ok(js.includes("el('coverageSummary')"), 'popup should render a live coverage summary');
assert.ok(js.includes("el('scarcityHints')"), 'popup should render dynamic result scarcity hints');
assert.ok(js.includes('12–20K'), 'strict salary explanation should include a concrete example');
assert.ok(js.includes('建议 2–3 页'), 'one-page searches should explain that coverage is limited');

console.log('Popup UX copy and guidance tests passed.');
