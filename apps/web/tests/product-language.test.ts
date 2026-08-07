import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {join, resolve} from "node:path";
import test from "node:test";

const webRoot = resolve(import.meta.dirname, "..");

async function source(path: string): Promise<string> {
  return readFile(join(webRoot, path), "utf8");
}

test("main navigation is organized around job seeker tasks instead of eval modules", async () => {
  const layout = await source("app/layout.tsx");
  assert.match(layout, />首页</);
  assert.match(layout, />我的背景</);
  assert.match(layout, />我的岗位</);
  assert.match(layout, />添加岗位</);
  assert.match(layout, /质量检查（高级）/);
  const primaryNav = layout.match(/<nav[\s\S]*?<\/nav>/)?.[0] ?? "";
  assert.doesNotMatch(primaryNav, /质量检查/);
  assert.doesNotMatch(layout, />画像评测</);
  assert.doesNotMatch(layout, />要求评测</);
});

test("profile primary copy uses user language and keeps implementation facts in technical details", async () => {
  const page = await source("app/profile/page.tsx");
  assert.match(page, /我的背景和求职偏好/);
  assert.match(page, /匹配准备情况/);
  assert.match(page, /careerContextReleaseLabel\(releaseReadiness\)/);
  assert.match(page, /查看技术详情/);
  assert.doesNotMatch(page, /未来 Match 的个人侧事实门禁/);
  assert.doesNotMatch(page, /本查询副作用/);
});

test("job detail defaults to user-facing requirement analysis and folds implementation metadata", async () => {
  const page = await source("app/jobs/[id]/page.tsx");
  assert.match(page, /岗位要求分析/);
  assert.match(page, /查看分析详情/);
  assert.doesNotMatch(page, /<span>Provider：/);
  assert.doesNotMatch(page, /<span className="code">Trace：/);
  assert.doesNotMatch(page, /confidence \{/);
});

test("home page explains the product as a simple job-search workflow", async () => {
  const page = await source("app/page.tsx");
  assert.match(page, /先把自己和岗位看清楚/);
  assert.match(page, /完善我的背景/);
  assert.match(page, /添加感兴趣的岗位/);
  assert.match(page, /查看岗位/);
  assert.doesNotMatch(page, /redirect\(/);
});
