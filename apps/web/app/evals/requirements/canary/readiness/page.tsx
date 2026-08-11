import Link from "next/link";

import {ServiceError} from "@/components/service-error";
import {
  BackendApiError,
  fetchRequirementAcceptanceReadiness,
} from "@/lib/backend";
import type {RequirementAcceptanceReadinessNextAction} from "@/lib/contracts";
import {
  requirementAcceptanceDatasetStateLabels,
  requirementAcceptanceNextActionClass,
} from "@/lib/requirement-acceptance-runs";

export const dynamic = "force-dynamic";

type SearchParams = {
  reviewer?: string | string[];
  title?: string | string[];
  maxNewExtractions?: string | string[];
};

type ActionCopy = {
  label: string;
  title: string;
  description: string;
};

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

function budget(value: string): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isInteger(parsed) && parsed >= 1 && parsed <= 20 ? parsed : 1;
}

function actionCopy(action: RequirementAcceptanceReadinessNextAction): ActionCopy {
  const copy: Record<RequirementAcceptanceReadinessNextAction, ActionCopy> = {
    fix_blockers: {
      label: "需要完成准备",
      title: "还需要完成几项准备工作",
      description:
        "系统暂时不会开始真实分析。先处理下面列出的事项，再重新检查即可。",
    },
    run_canary: {
      label: "可以开始小规模测试",
      title: "已经可以开始小规模真实测试",
      description:
        "关键准备工作已经完成。下一步会先用少量岗位验证真实分析链路，避免一次处理过多内容。",
    },
    review_canary: {
      label: "等待你的确认",
      title: "需要你确认这轮测试结果",
      description:
        "系统已经拿到真实分析结果，现在需要人工看一眼结果是否可信，再决定是否继续。",
    },
    resume_run: {
      label: "可以继续测试",
      title: "可以继续处理剩余测试岗位",
      description:
        "上一轮结果已经得到人工确认，可以按受控方式继续，不会跳过既有审核记录。",
    },
    open_manual_review: {
      label: "等待最终人工检查",
      title: "20 个岗位已准备好做最终人工检查",
      description:
        "真实分析已经完成到可以集中检查的阶段。下一步确认岗位要求提取是否准确、是否值得进入后续匹配。",
    },
    stopped: {
      label: "本轮已停止",
      title: "本轮真实测试已经停止",
      description:
        "系统会保留已有结果和停止原因，不会自动重试或覆盖之前的人工决定。",
    },
  };
  return copy[action];
}

function friendlyBlocker(code: string): string {
  const messages: Record<string, string> = {
    database_unreachable: "暂时无法读取本地数据，请确认本地服务和数据库可以正常访问。",
    database_migration_not_current: "本地数据结构还没有更新到当前版本。",
    live_provider_not_configured: "真实 AI 分析服务还没有配置完成。",
    live_model_not_configured: "还没有选择用于真实岗位分析的 AI 模型。",
    reviewer_missing: "请填写审核人，方便之后知道这轮结果由谁确认。",
    title_missing: "请填写本轮测试名称，方便之后查找和回顾。",
    openai_api_key_missing: "真实 AI 分析服务还没有可用的访问凭据。",
    max_new_extractions_missing: "请设置这轮最多处理多少个新岗位。",
    max_new_extractions_out_of_range: "本轮测试数量超出安全范围，请调整后重新检查。",
    initial_canary_limit_exceeded: "首次真实测试数量过多，请先从少量岗位开始。",
    remaining_canary_limit_exceeded: "本轮剩余可安全测试的岗位数量不足，请降低本次处理数量。",
  };
  return messages[code] ?? "还有一项系统准备工作没有完成，可在下方技术详情中查看原因。";
}

export default async function RequirementAcceptanceReadinessPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const reviewer = first(params.reviewer).trim();
  const title = first(params.title).trim();
  const maxNewExtractions = budget(first(params.maxNewExtractions));
  const backendQuery = new URLSearchParams({
    max_new_extractions: String(maxNewExtractions),
  });
  if (reviewer) backendQuery.set("reviewer", reviewer);
  if (title) backendQuery.set("title", title);

  let readiness;
  try {
    readiness = await fetchRequirementAcceptanceReadiness(backendQuery);
  } catch (caught) {
    const message =
      caught instanceof BackendApiError
        ? caught.message
        : "读取岗位要求分析准备情况时发生未知错误。";
    return <ServiceError message={message} />;
  }

  const next = actionCopy(readiness.nextAction);
  const systemReady = readiness.workflowReady && readiness.blockers.length === 0;
  const needsReviewIdentity = readiness.blockers.some(
    (blocker) => blocker.code === "reviewer_missing" || blocker.code === "title_missing",
  );

  return (
    <>
      <section className="page-heading readiness-page-heading">
        <p className="eyebrow">Quality check</p>
        <h1>岗位要求分析准备情况</h1>
        <p className="lede">
          这个页面只回答三个问题：现在能不能继续、为什么，以及下一步做什么。
          系统检查本身不会开始真实 AI 分析，也不会修改你的岗位数据。
        </p>
        <div className="actions">
          <Link className="button-ghost" href="/jobs">
            返回我的岗位
          </Link>
          <Link className="button-ghost" href="/evals/requirements/canary">
            查看历史测试
          </Link>
        </div>
      </section>

      <section className="readiness-overview">
        <div className="readiness-overview-copy">
          <span
            className={`status-chip ${requirementAcceptanceNextActionClass(readiness.nextAction)}`}
          >
            {next.label}
          </span>
          <h2>{next.title}</h2>
          <p>{next.description}</p>
        </div>
        <div className="readiness-overview-status">
          <span>当前状态</span>
          <strong>{systemReady ? "准备完成" : "需要关注"}</strong>
          <small>
            {readiness.blockers.length === 0
              ? "没有发现新的准备问题"
              : `还有 ${readiness.blockers.length} 项需要处理`}
          </small>
        </div>
      </section>

      <section className="detail-card">
        <div className="section-heading-row readiness-section-heading">
          <div>
            <p className="eyebrow">Progress</p>
            <h2>目前进行到哪里</h2>
          </div>
        </div>
        <div className="readiness-progress-grid">
          <article>
            <span>测试岗位</span>
            <strong>{readiness.selectedCount}/20</strong>
            <p>固定样本用于检查岗位要求分析是否稳定。</p>
          </article>
          <article>
            <span>系统准备</span>
            <strong>{readiness.workflowReady ? "已完成" : "未完成"}</strong>
            <p>包括数据、配置和已有测试记录是否可以安全衔接。</p>
          </article>
          <article>
            <span>真实测试次数</span>
            <strong>{readiness.attemptedCalls}</strong>
            <p>只统计真实分析尝试，不把页面检查算进去。</p>
          </article>
        </div>
      </section>

      <section className="detail-card readiness-next-step-card">
        <p className="eyebrow">Next step</p>
        <h2>下一步做什么</h2>

        {readiness.nextAction === "review_canary" && readiness.workbenchUrl ? (
          <>
            <p>打开本轮结果，检查岗位原文与提取结果是否一致，再决定继续或停止。</p>
            <div className="actions">
              <a className="button" href={readiness.workbenchUrl}>
                审核本轮测试结果
              </a>
            </div>
          </>
        ) : null}

        {readiness.nextAction === "open_manual_review" &&
        readiness.manualReviewUrl ? (
          <>
            <p>集中检查 20 个岗位的要求分析质量，完成后才会允许进入正式岗位匹配。</p>
            <div className="actions">
              <a className="button" href={readiness.manualReviewUrl}>
                开始 20 个岗位人工检查
              </a>
            </div>
          </>
        ) : null}

        {readiness.nextAction === "run_canary" ||
        readiness.nextAction === "resume_run" ? (
          <p className="notice">
            当前已经满足下一轮受控测试条件。为了避免误触发真实 AI 调用，这里只显示状态；实际执行仍由安全运行流程完成。
          </p>
        ) : null}

        {readiness.nextAction === "fix_blockers" ? (
          <p className="notice">先处理下面的准备事项，然后点击“重新检查状态”。</p>
        ) : null}

        {readiness.nextAction === "stopped" ? (
          <p className="notice">
            这轮测试已按人工决定停止。已有结果会保留，不会在这个页面自动重新开始。
          </p>
        ) : null}
      </section>

      <section className="detail-card">
        <p className="eyebrow">Needs attention</p>
        <h2>需要处理的事项</h2>
        {readiness.blockers.length === 0 ? (
          <div className="success-box readiness-success-box">
            当前没有发现阻塞项。你可以按照上面的“下一步”继续。
          </div>
        ) : (
          <>
            <ul className="readiness-blocker-list">
              {readiness.blockers.map((blocker) => (
                <li key={`${blocker.scope}-${blocker.code}`}>
                  <span aria-hidden="true">!</span>
                  <div>
                    <strong>{friendlyBlocker(blocker.code)}</strong>
                    <p>处理完成后重新检查状态即可。</p>
                  </div>
                </li>
              ))}
            </ul>
            {needsReviewIdentity ? (
              <form className="readiness-user-input-form" method="get">
                <div>
                  <h3>确认本轮测试信息</h3>
                  <p>这两个字段只用于记录和回查，不会启动真实 AI 分析。</p>
                </div>
                <label>
                  你的名字
                  <input
                    defaultValue={reviewer}
                    name="reviewer"
                    placeholder="例如 will"
                    type="text"
                  />
                </label>
                <label>
                  本轮测试名称
                  <input
                    defaultValue={title}
                    name="title"
                    placeholder="例如 8 月岗位要求质量检查"
                    type="text"
                  />
                </label>
                <input
                  name="maxNewExtractions"
                  type="hidden"
                  value={String(maxNewExtractions)}
                />
                <button className="button" type="submit">
                  保存并重新检查
                </button>
              </form>
            ) : null}
          </>
        )}
      </section>

      <details className="readiness-advanced-details">
        <summary>技术详情与运行参数</summary>
        <div className="readiness-advanced-content">
          <p className="muted">
            下面的信息主要用于开发和排查。普通使用时不需要理解这些字段，也不会从这里触发真实 AI 调用。
          </p>

          <form className="readiness-settings-form" method="get">
            <label>
              审核人
              <input
                defaultValue={reviewer}
                name="reviewer"
                placeholder="例如 will"
                type="text"
              />
            </label>
            <label>
              本轮测试名称
              <input
                defaultValue={title}
                name="title"
                placeholder="留空时自动生成"
                type="text"
              />
            </label>
            <label>
              本轮最多新增测试数
              <input
                defaultValue={String(maxNewExtractions)}
                max={20}
                min={1}
                name="maxNewExtractions"
                type="number"
              />
            </label>
            <div className="actions readiness-settings-action">
              <button className="button-secondary" type="submit">
                重新检查状态
              </button>
            </div>
          </form>

          <div className="readiness-advanced-grid">
            <div>
              <span>正式数据集</span>
              <strong>
                {requirementAcceptanceDatasetStateLabels[readiness.datasetState]}
              </strong>
              <small>{readiness.datasetFileName ?? "—"}</small>
            </div>
            <div>
              <span>数据库版本</span>
              <strong className="code">{readiness.databaseRevision ?? "—"}</strong>
              <small className="code">Head {readiness.migrationHead}</small>
            </div>
            <div>
              <span>AI 服务 / 模型</span>
              <strong>{readiness.provider || "未配置"}</strong>
              <small>{readiness.model || "未配置模型"}</small>
            </div>
            <div>
              <span>访问凭据</span>
              <strong>{readiness.apiKeyConfigured ? "已配置" : "未配置"}</strong>
              <small>这里只显示是否存在，不显示密钥</small>
            </div>
            <div>
              <span>Dataset fingerprint</span>
              <strong className="code">{readiness.datasetFingerprint ?? "—"}</strong>
            </div>
            <div>
              <span>Run / Batch</span>
              <strong className="code">{readiness.runId ?? "—"}</strong>
              <small className="code">{readiness.batchId ?? "—"}</small>
            </div>
            <div>
              <span>页面检查副作用</span>
              <strong>
                DB writes {readiness.dbWrites} / Provider calls {readiness.providerCalls}
              </strong>
            </div>
            <div>
              <span>当前审核信息</span>
              <strong>{readiness.reviewer || "未填写审核人"}</strong>
              <small>{readiness.title || "未填写测试名称"}</small>
            </div>
          </div>

          {readiness.blockers.length > 0 ? (
            <div className="readiness-technical-blockers">
              <h3>技术阻塞详情</h3>
              <ul>
                {readiness.blockers.map((blocker) => (
                  <li key={`technical-${blocker.scope}-${blocker.code}`}>
                    <strong className="code">{blocker.code}</strong>
                    <p>{blocker.message}</p>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </details>
    </>
  );
}
