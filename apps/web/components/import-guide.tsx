import Link from "next/link";

const armourInstallSteps = [
  {
    title: "打开 Chrome 扩展管理页",
    body: "在 Chrome 地址栏输入 chrome://extensions/ 打开扩展管理页。",
  },
  {
    title: "开启开发者模式",
    body: "打开页面右上角的「开发者模式」开关，才会出现「加载已解压的扩展程序」按钮。",
  },
  {
    title: "加载项目里的插件目录",
    body: "点击「加载已解压的扩展程序」，选择本仓库里的 apps/collector-extension 目录。",
  },
  {
    title: "确认安装成功",
    body: "扩展列表里出现「岗位筛选」，版本为 v1.4.6，即安装成功。",
  },
];

const collectionSteps = [
  {
    title: "登录并进入目标站点",
    body: "让当前 Chrome 处于已登录 BOSS 直聘的状态，插件只在这个站点的页面上运行。",
  },
  {
    title: "填写搜索词",
    body: "每行一个。默认内置一组 AI / 大模型方向关键词模板，也可以删掉换成任何岗位方向。",
  },
  {
    title: "选择城市与远程范围",
    body: "最多同时选 20 个城市；「全国远程」是独立搜索范围，可单独勾选。",
  },
  {
    title: "设置薪资等筛选条件",
    body: "按薪资下限、薪资模式、相关度等过滤，可选排除兼职、实习、助理。",
  },
  {
    title: "开始搜索",
    body: "点击弹窗里的「开始搜索并自动导出」，任务会在新标签页运行，完成后自动下载导出文件。",
  },
];

export function ImportGuide() {
  return (
    <section className="guide-panel" aria-label="浏览器插件使用指南">
      <p className="eyebrow">先从浏览器插件开始</p>
      <h2>从收集岗位到用起来了，整个流程是这样连起来的</h2>
      <p className="lede">
        JobLens 的所有判断都以真实岗位数据为前提。岗位数据由项目自带的浏览器插件
        「岗位筛选」在你已登录的求职网站上收集，再通过导入进入 JobLens
        的分析流程。下面按完整顺序讲清楚：插件是什么、怎么装、怎么用，以及岗位数据怎么进到 JobLens。
      </p>

      <div className="guide-flow" aria-label="JobLens 完整流程">
        <article className="guide-flow-step">
          <span className="guide-flow-num">1</span>
          <h3>确认背景与偏好</h3>
          <p>在<a href="/profile">我的背景</a>确认经历、技能和求职偏好，之后的判断都从这里出发。</p>
        </article>
        <article className="guide-flow-step">
          <span className="guide-flow-num">2</span>
          <h3>插件收集岗位</h3>
          <p>在已登录 BOSS 直聘的浏览器里，让「岗位筛选」插件按关键词、城市和薪资批量收集真实岗位。</p>
        </article>
        <article className="guide-flow-step">
          <span className="guide-flow-num">3</span>
          <h3>导出或同步报告</h3>
          <p>插件运行完会自动下载「完整报告」JSON；也可以直接在插件里点「同步到 JobLens」直连本机后端。</p>
        </article>
        <article className="guide-flow-step">
          <span className="guide-flow-num">4</span>
          <h3>导入岗位到 JobLens</h3>
          <p>用本页下方的表单上传导出的 JSON，或在插件里点「查看本次导入」直接跳到导入结果。</p>
        </article>
        <article className="guide-flow-step">
          <span className="guide-flow-num">5</span>
          <h3>查看岗位与分析要求</h3>
          <p>在<a href="/jobs">我的岗位</a>浏览岗位、核对 JD，系统会提取岗位的硬性要求。</p>
        </article>
        <article className="guide-flow-step">
          <span className="guide-flow-num">6</span>
          <h3>看优先投递排序</h3>
          <p>在<a href="/recommendations">优先投递</a>查看结合真实经历与岗位要求给出的排序和理由。</p>
        </article>
      </div>

      <div className="guide-section">
        <h3>插件是什么</h3>
        <p>
          「岗位筛选」v1.4.6 是项目自带的 Chrome 插件，位于仓库的
          <span className="code">apps/collector-extension</span>。它专门负责
          <strong>收集与整理真实岗位数据</strong>，不负责职业判断，也不会自动投递岗位。
        </p>
        <ul className="guide-list">
          <li>按关键词批量搜索，默认内置 AI / 大模型方向关键词模板，可替换成任意岗位方向；</li>
          <li>多城市搜索（最多 20 个城市）与「全国远程」识别，自动去重；</li>
          <li>解析 BOSS 直聘的混淆薪资，并按薪资下限、岗位相关度过滤；</li>
          <li>自动打开详情页补充完整 JD，并标记 <span className="code">full_jd / partial_jd / card_only</span> 质量；</li>
          <li>一键导出 CSV、完整报告 JSON、诊断 JSON 与 Requirement 验收数据。</li>
        </ul>
      </div>

      <div className="guide-section">
        <h3>第一次怎么安装</h3>
        <ol className="guide-steps">
          {armourInstallSteps.map((step) => (
            <li key={step.title}>
              <strong>{step.title}</strong>
              <span>{step.body}</span>
            </li>
          ))}
        </ol>
        <p className="guide-note">
          插件以「加载已解压的扩展程序」方式运行，改动代码后回到 <span className="code">chrome://extensions/</span> 点击「重新加载」即可生效。
        </p>
      </div>

      <div className="guide-section">
        <h3>怎么用插件收集岗位</h3>
        <ol className="guide-steps">
          {collectionSteps.map((step) => (
            <li key={step.title}>
              <strong>{step.title}</strong>
              <span>{step.body}</span>
            </li>
          ))}
        </ol>
      </div>

      <div className="guide-section">
        <h3>把岗位数据带进 JobLens</h3>
        <p>运行完成后，有两条路径把岗位数据交给 JobLens：</p>
        <div className="guide-method-grid">
          <article className="guide-method">
            <h4>路径 A：在插件里直接同步（推荐）</h4>
            <p>
              在插件弹窗点「同步到 JobLens」，插件会把完整报告 POST 到本机后端
              <span className="code">http://127.0.0.1:8000/api/v1/job-imports</span>。
              同步成功后点「查看本次导入」就能跳到这次的导入结果页。
            </p>
          </article>
          <article className="guide-method">
            <h4>路径 B：下载报告后在本页上传</h4>
            <p>
              在插件里点「完整报告」下载 <span className="code">boss-job-filter-report-*.json</span>，
              然后用本页下方的表单上传。系统会自动去重并保留原始岗位链接。
            </p>
          </article>
        </div>
        <p className="guide-note">
          同步需要本机后端正在运行（<span className="code">services/backend</span> 的 <span className="code">uv run fastapi dev</span>）。
          后端没有启动时，同步会提示失败，此时用路径 B 上传 JSON 即可。
        </p>
      </div>

      <div className="guide-section">
        <h3>接下来</h3>
        <p>
          岗位导入后，就可以按顺序浏览流程：先看
          <a href="/jobs">我的岗位</a>核对数据，再回到
          <a href="/recommendations">优先投递</a>看看哪些岗位最值得先投、以及为什么。
        </p>
      </div>
    </section>
  );
}