"use client";

import Link from "next/link";
import {FormEvent, useEffect, useMemo, useState} from "react";

import {formatDateTime, formatSalary} from "@/lib/format";
import {matchRecommendationLabels} from "@/lib/match-report";
import type {MatchRecommendation} from "@/lib/contracts";

type FeedbackDecision = "interested" | "maybe" | "rejected";

type CohortCandidate = {
  feedbackId: string | null;
  jobId: string;
  title: string;
  company: string;
  area: string | null;
  salaryMinK: number | null;
  salaryMaxK: number | null;
  decision: FeedbackDecision | null;
  feedbackCreatedAt: string | null;
  reasons: string[];
  note: string | null;
  recommendation: MatchRecommendation | null;
  matchSummary: string | null;
};

type CandidateResponse = {
  items: CohortCandidate[];
  totalFeedbackRecords: number;
  latestJobFeedbackCount: number;
  excludedRejectedJobCount: number;
  totalJobCount: number;
  feedbackOverlayAvailable: boolean;
};

type GapItem = {
  capability: string;
  priority: "P0" | "P1" | string;
  whyImportant: Record<string, number>;
  supportingRequirementIds: string[];
  supportingJobIds: string[];
  profileSkillIds: string[];
  evidenceIds: string[];
  currentState: string;
  completionCriteria: string[];
};

type GapResponse = {
  cohortId: string;
  jobIds: string[];
  factsUsable: boolean;
  profileId: string | null;
  profileVersion: number | null;
  items: GapItem[];
  blockers: string[];
};

type ParsedGapBlocker = {
  raw: string;
  jobId: string | null;
  code: string;
};

type GapBlockerCopy = {
  title: string;
  description: string;
  actionHref?: string;
  actionLabel?: string;
};

const decisionLabels: Record<FeedbackDecision, string> = {
  interested: "感兴趣",
  maybe: "再看看",
  rejected: "不考虑",
};

const reasonLabels: Record<string, string> = {
  role_fit: "方向匹配",
  skill_gap: "有能力差距",
  compensation: "薪资因素",
  location: "地点因素",
  seniority: "职级因素",
  company: "公司因素",
  work_mode: "办公方式",
  other: "其他",
};

const completionCriteriaLabels: Record<string, string> = {
  confirmed_profile_skill_exists: "在已确认职业背景中补充并确认这项能力",
  confirmed_evidence_linked_to_skill_exists: "至少补充 1 条可核验的工作或项目证据，并与这项能力关联",
};

function currentStateLabel(value: string): string {
  if (value === "missing" || value === "capability_missing") return "当前职业背景里还没有确认这项能力。";
  if (value === "skill_exists_without_confirmed_evidence") {
    return "你已经写过这项能力，但还缺少可核验的项目或工作证据。";
  }
  return value;
}

function completionCriterionLabel(value: string): string {
  return completionCriteriaLabels[value] ?? value;
}

const SAFE_FACT_ID = /^[A-Za-z0-9_-]{1,120}$/;

function buildGapEvidenceHref(item: GapItem): string | null {
  if (item.priority !== "P0") return null;

  const supportingJobIds = Array.from(new Set(item.supportingJobIds.filter((id) => SAFE_FACT_ID.test(id))));
  const supportingRequirementIds = Array.from(
    new Set(item.supportingRequirementIds.filter((id) => SAFE_FACT_ID.test(id))),
  );
  const focusJobId = supportingJobIds[0];
  const focusRequirementId = supportingRequirementIds[0];
  const focusCapability = item.capability.trim().slice(0, 120);
  if (!focusJobId || !focusRequirementId || !focusCapability) return null;

  const query = new URLSearchParams({
    next: "/recommendations",
    focusRequirement: "skill",
    focusJob: focusJobId,
    focusRequirementId,
    focusCapability,
    focusImpactJobs: supportingJobIds.slice(0, 3).join(","),
    focusImpactRequirementIds: supportingRequirementIds.slice(0, 20).join(","),
  });
  return `/profile?${query.toString()}`;
}

function buildGapPreparationHref(item: GapItem, jobId: string): string {
  const query = new URLSearchParams();
  const supportingJobIds = Array.from(new Set(item.supportingJobIds.filter((id) => SAFE_FACT_ID.test(id))));
  const supportingRequirementIds = Array.from(
    new Set(item.supportingRequirementIds.filter((id) => SAFE_FACT_ID.test(id))),
  );
  if (supportingJobIds.length > 0) query.set("focusImpactJobs", supportingJobIds.slice(0, 3).join(","));
  if (supportingRequirementIds.length > 0) {
    query.set("focusImpactRequirementIds", supportingRequirementIds.slice(0, 20).join(","));
  }
  return `/jobs/${jobId}/prepare?${query.toString()}`;
}

function parseGapBlocker(value: string): ParsedGapBlocker {
  const separatorIndex = value.indexOf(":");
  if (separatorIndex <= 0) {
    return {raw: value, jobId: null, code: value};
  }
  return {
    raw: value,
    jobId: value.slice(0, separatorIndex),
    code: value.slice(separatorIndex + 1),
  };
}

function gapBlockerCopy(code: string): GapBlockerCopy {
  if (code === "profile_missing") {
    return {
      title: "你的职业背景还没有准备好",
      description: "先补充并确认你的技能、项目和工作证据。确认后的真实经历才会参与能力差距判断。",
      actionHref: "/profile",
      actionLabel: "完善我的职业背景",
    };
  }
  if (code === "accepted_baseline_missing") {
    return {
      title: "岗位要求还没有完成质量确认",
      description: "这些岗位已经有要求分析结果，但当前版本还没有完成正式质量确认，所以暂时不能把它们当作可靠事实与你的经历比较。",
      actionHref: "/evals/requirements/canary/readiness",
      actionLabel: "查看岗位要求准备状态",
    };
  }
  if (code === "requirement_extraction_missing") {
    return {
      title: "有些岗位还没有完成要求分析",
      description: "先打开下面的岗位完成“分析岗位要求”，再回来做共同能力差距分析。",
    };
  }
  if (code === "extraction_input_stale") {
    return {
      title: "岗位描述更新了，需要重新分析",
      description: "当前保存的岗位要求对应旧版 JD。重新分析后，JobLens 才能确保比较的是最新岗位要求。",
    };
  }
  if (code === "extraction_cohort_mismatch") {
    return {
      title: "岗位要求来自旧的分析版本",
      description: "当前要求分析与已经确认的质量版本不一致，需要重新完成要求分析或质量确认。",
      actionHref: "/evals/requirements/canary/readiness",
      actionLabel: "查看岗位要求准备状态",
    };
  }
  if (
    code === "requirements_empty" ||
    code === "requirement_count_mismatch" ||
    code === "trace_missing" ||
    code === "trace_failed" ||
    code === "trace_capability_mismatch" ||
    code === "trace_cohort_mismatch" ||
    code === "trace_input_mismatch" ||
    code === "trace_output_mismatch" ||
    code === "release_identity_changed"
  ) {
    return {
      title: "岗位要求分析还没有通过完整性检查",
      description: "系统发现岗位要求的分析记录、来源或追踪证据还不完整。为避免给你错误的学习建议，当前先不生成技能差距。",
      actionHref: "/evals/requirements/canary/readiness",
      actionLabel: "查看岗位要求准备状态",
    };
  }
  return {
    title: "能力差距的分析依据还没有准备完整",
    description: "JobLens 暂时无法安全使用其中一部分事实。技术原因已保留在下方，普通使用时不需要理解错误码。",
  };
}

export function TargetCohortGapPanel() {
  const [candidates, setCandidates] = useState<CandidateResponse | null>(null);
  const [candidateError, setCandidateError] = useState<string | null>(null);
  const [loadingCandidates, setLoadingCandidates] = useState(true);
  const [selectedJobIds, setSelectedJobIds] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | FeedbackDecision>("all");
  const [result, setResult] = useState<GapResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function loadCandidates() {
      setLoadingCandidates(true);
      setCandidateError(null);
      try {
        const response = await fetch("/api/target-cohort/gaps", {method: "GET"});
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload?.error?.message ?? "暂时无法读取可选岗位。");
        }
        if (!cancelled) setCandidates(payload as CandidateResponse);
      } catch (caught) {
        if (!cancelled) {
          setCandidateError(caught instanceof Error ? caught.message : "暂时无法读取可选岗位。");
        }
      } finally {
        if (!cancelled) setLoadingCandidates(false);
      }
    }
    void loadCandidates();
    return () => {
      cancelled = true;
    };
  }, []);

  const visibleCandidates = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase("zh-CN");
    return (candidates?.items ?? []).filter((item) => {
      if (filter !== "all" && item.decision !== filter) return false;
      if (!normalizedQuery) return true;
      return [item.title, item.company, item.area ?? ""]
        .join(" ")
        .toLocaleLowerCase("zh-CN")
        .includes(normalizedQuery);
    });
  }, [candidates, filter, query]);

  const selectedCandidates = useMemo(() => {
    const selected = selectedJobIds;
    return (candidates?.items ?? []).filter((item) => selected.has(item.jobId));
  }, [candidates, selectedJobIds]);

  const candidateByJobId = useMemo(
    () => new Map((candidates?.items ?? []).map((item) => [item.jobId, item])),
    [candidates],
  );

  const blockerGroups = useMemo(() => {
    const groups = new Map<string, ParsedGapBlocker[]>();
    for (const raw of result?.blockers ?? []) {
      const blocker = parseGapBlocker(raw);
      const current = groups.get(blocker.code) ?? [];
      current.push(blocker);
      groups.set(blocker.code, current);
    }
    return [...groups.entries()].map(([code, blockers]) => ({
      code,
      blockers,
      copy: gapBlockerCopy(code),
    }));
  }, [result]);

  function toggleCandidate(jobId: string) {
    setSelectedJobIds((current) => {
      const next = new Set(current);
      if (next.has(jobId)) next.delete(jobId);
      else next.add(jobId);
      return next;
    });
    setResult(null);
    setError(null);
  }

  function selectInterested() {
    setSelectedJobIds(
      new Set((candidates?.items ?? []).filter((item) => item.decision === "interested").map((item) => item.jobId)),
    );
    setResult(null);
    setError(null);
  }

  function clearSelection() {
    setSelectedJobIds(new Set());
    setResult(null);
    setError(null);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (selectedJobIds.size === 0) {
      setError("请先选择至少一个你真正想作为目标的岗位。");
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const response = await fetch("/api/target-cohort/gaps", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          cohortId: `target-cohort-${Date.now()}`,
          name: "我的目标岗位",
          selectedJobIds: [...selectedJobIds],
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        setError(payload?.error?.message ?? payload?.detail?.message ?? "暂时无法生成能力差距，请刷新候选岗位后重试。");
        return;
      }
      setResult(payload as GapResponse);
    } catch {
      setError("暂时无法连接分析服务，请稍后重试。");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="gap-workspace">
      <section className="gap-selector-card">
        <div className="gap-selector-header">
          <div>
            <span className="eyebrow">第 1 步 · 选择目标岗位</span>
            <h2>哪些岗位值得拿来规划下一阶段能力？</h2>
            <p>
              直接从你的岗位池里选择真正想投入时间准备的目标。已有“感兴趣 / 再看看 / 不考虑”反馈会作为辅助信息展示；你选的是岗位，不需要再找任何 ID。
            </p>
          </div>
          {candidates ? (
            <div className="gap-source-summary" aria-label="候选岗位统计">
              <strong>{candidates.items.length}</strong>
              <span>个可选岗位</span>
              {candidates.excludedRejectedJobCount > 0 ? (
                <small>{candidates.excludedRejectedJobCount} 个岗位的最新反馈为“不考虑”</small>
              ) : null}
            </div>
          ) : null}
        </div>

        {loadingCandidates ? (
          <div className="gap-empty-state">正在整理你的岗位池…</div>
        ) : candidateError ? (
          <div className="inline-error" role="alert">{candidateError}</div>
        ) : candidates && candidates.items.length === 0 ? (
          <div className="gap-empty-state gap-empty-action">
            <div>
              <strong>岗位池里还没有可以选择的真实岗位</strong>
              <p>先添加或导入你真正考虑的岗位。是否已经留下“感兴趣 / 再看看”反馈，不影响你手动把岗位选进目标集合。</p>
            </div>
            <Link className="button" href="/import">添加岗位</Link>
          </div>
        ) : (
          <form onSubmit={submit}>
            <div className="gap-toolbar">
              <div className="gap-filter-tabs" aria-label="岗位反馈筛选">
                {([
                  ["all", "全部"],
                  ["interested", "感兴趣"],
                  ["maybe", "再看看"],
                  ["rejected", "不考虑"],
                ] as const).map(([value, label]) => (
                  <button
                    className={filter === value ? "gap-filter-tab is-active" : "gap-filter-tab"}
                    key={value}
                    onClick={() => setFilter(value)}
                    type="button"
                  >
                    {label}
                  </button>
                ))}
              </div>
              <label className="gap-search-field">
                <span className="sr-only">搜索岗位</span>
                <input
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="搜索岗位、公司或地点"
                  type="search"
                  value={query}
                />
              </label>
            </div>

            <div className="gap-quick-actions">
              <button className="button-ghost" onClick={selectInterested} type="button">选择全部“感兴趣”</button>
              {selectedJobIds.size > 0 ? (
                <button className="button-ghost" onClick={clearSelection} type="button">清空选择</button>
              ) : null}
              <span>建议选 3～8 个你真正愿意投入时间准备的岗位，结果会更聚焦。</span>
            </div>

            {visibleCandidates.length === 0 ? (
              <div className="gap-empty-state">没有符合当前筛选条件的岗位。</div>
            ) : (
              <div className="gap-candidate-grid">
                {visibleCandidates.map((item) => {
                  const selected = selectedJobIds.has(item.jobId);
                  return (
                    <label className={selected ? "gap-candidate-card is-selected" : "gap-candidate-card"} key={item.jobId}>
                      <input
                        checked={selected}
                        onChange={() => toggleCandidate(item.jobId)}
                        type="checkbox"
                      />
                      <span className="gap-card-check" aria-hidden="true">{selected ? "✓" : ""}</span>
                      <div className="gap-candidate-main">
                        <div className="gap-candidate-title-row">
                          <div>
                            <strong>{item.title}</strong>
                            <span>{item.company}</span>
                          </div>
                          {item.decision ? (
                            <span className={`gap-decision-pill decision-${item.decision}`}>
                              {decisionLabels[item.decision]}
                            </span>
                          ) : (
                            <span className="gap-decision-pill">未表态</span>
                          )}
                        </div>
                        <div className="gap-job-meta">
                          <span>{formatSalary(item.salaryMinK, item.salaryMaxK)}</span>
                          {item.area ? <span>{item.area}</span> : null}
                          {item.feedbackCreatedAt ? <span>反馈于 {formatDateTime(item.feedbackCreatedAt)}</span> : null}
                        </div>
                        {item.recommendation ? (
                          <div className="gap-match-snapshot">
                            <span>{matchRecommendationLabels[item.recommendation]}</span>
                            {item.matchSummary ? <p>{item.matchSummary}</p> : null}
                          </div>
                        ) : null}
                        {(item.reasons.length > 0 || item.note) ? (
                          <div className="gap-feedback-reasons">
                            {item.reasons.map((reason) => <span key={reason}>{reasonLabels[reason] ?? reason}</span>)}
                            {item.note ? <small>{item.note}</small> : null}
                          </div>
                        ) : null}
                      </div>
                    </label>
                  );
                })}
              </div>
            )}

            <div className="gap-selection-bar">
              <div>
                <strong>已选择 {selectedJobIds.size} 个目标岗位</strong>
                <p>
                  {selectedCandidates.length > 0
                    ? selectedCandidates.slice(0, 3).map((item) => item.title).join("、") + (selectedCandidates.length > 3 ? ` 等 ${selectedCandidates.length} 个` : "")
                    : "先选岗位，再查看哪些能力最值得优先补。"}
                </p>
              </div>
              <button className="button" disabled={loading || selectedJobIds.size === 0} type="submit">
                {loading ? "正在分析能力差距…" : "分析这些岗位的共同能力差距"}
              </button>
            </div>
          </form>
        )}
      </section>

      {error ? <p className="inline-error" role="alert">{error}</p> : null}

      {result ? (
        <section className="gap-results-section">
          <div className="gap-results-header">
            <div>
              <span className="eyebrow">第 2 步 · 看清优先级</span>
              <h2>这些目标岗位最值得补什么？</h2>
              <p>基于 {result.jobIds.length} 个你亲自选择的岗位，以及当前已确认的职业证据。</p>
            </div>
            {result.factsUsable ? <span className="gap-ready-badge">事实已通过使用门槛</span> : null}
          </div>

          {!result.factsUsable ? (
            <div className="gap-blocked-card">
              <div className="gap-blocked-intro">
                <span className="gap-blocked-kicker">还差一步准备</span>
                <strong>现在卡住的不是你的技能，而是分析依据还没准备完整</strong>
                <p>
                  这不是你的技能缺口。JobLens 不会在岗位要求尚未确认时先猜“你缺什么”，否则很容易把模型误差变成你的学习任务。
                </p>
              </div>

              <div className="gap-readiness-grid">
                <article className={result.profileId ? "gap-readiness-state is-ready" : "gap-readiness-state is-blocked"}>
                  <span>你的职业背景</span>
                  <strong>{result.profileId ? "已准备" : "还需补充"}</strong>
                  <p>
                    {result.profileId
                      ? "你的职业背景已确认，可以用于对比。当前不用为了这个错误去随意补技能或项目。"
                      : "需要先确认你的技能、项目和工作证据，系统才知道你现在已经具备什么。"}
                  </p>
                </article>
                <article className="gap-readiness-state is-blocked">
                  <span>目标岗位要求</span>
                  <strong>暂未全部准备好</strong>
                  <p>至少一个目标岗位的要求分析还没有达到可用于能力规划的可信状态。</p>
                </article>
              </div>

              {blockerGroups.length > 0 ? (
                <div className="gap-blocker-list">
                  {blockerGroups.map(({code, blockers, copy}) => {
                    const affectedJobs = blockers
                      .map((blocker) => blocker.jobId ? candidateByJobId.get(blocker.jobId) : null)
                      .filter((candidate): candidate is CohortCandidate => Boolean(candidate));
                    return (
                      <article className="gap-blocker-item" key={code}>
                        <div>
                          <strong>{copy.title}</strong>
                          <p>{copy.description}</p>
                        </div>
                        {affectedJobs.length > 0 ? (
                          <div className="gap-blocker-jobs">
                            <span>受影响的岗位</span>
                            {affectedJobs.map((job) => (
                              <Link href={`/jobs/${job.jobId}`} key={job.jobId}>
                                {job.title} · {job.company}
                              </Link>
                            ))}
                          </div>
                        ) : null}
                        {copy.actionHref && copy.actionLabel ? (
                          <div className="actions">
                            <Link className="button-ghost" href={copy.actionHref}>{copy.actionLabel}</Link>
                          </div>
                        ) : null}
                      </article>
                    );
                  })}
                </div>
              ) : null}

              <div className="gap-next-preview">
                <strong>准备完成后，你会在这里直接看到</strong>
                <ul>
                  <li>哪些技能是真正缺失，哪些只是“会但缺项目证据”；</li>
                  <li>每项技能是 P0 还是 P1，以及它影响多少个目标岗位；</li>
                  <li>你当前已有的真实证据，以及做到什么才算补齐。</li>
                </ul>
              </div>

              {result.blockers.length > 0 ? (
                <details className="gap-technical-blockers">
                  <summary>查看技术原因</summary>
                  <ul>{result.blockers.map((item) => <li key={item}>{item}</li>)}</ul>
                </details>
              ) : null}
            </div>
          ) : result.items.length === 0 ? (
            <div className="gap-empty-state">
              <strong>当前没有识别到需要优先补齐的能力差距。</strong>
              <p>这不代表“完全匹配”，而是当前已确认事实下没有形成 P0/P1 补强项。</p>
            </div>
          ) : (
            <div className="gap-result-grid">
              {result.items.map((item, index) => {
                const supportingJobs = item.supportingJobIds
                  .map((jobId) => candidateByJobId.get(jobId))
                  .filter((candidate): candidate is CohortCandidate => Boolean(candidate));
                const coverage = Math.round((item.whyImportant.targetCoverage ?? 0) * 100);
                const mustHaveRatio = Math.round((item.whyImportant.mustHaveRatio ?? 0) * 100);
                const evidenceHref = buildGapEvidenceHref(item);
                return (
                  <article className="gap-result-card" key={item.capability}>
                    <div className="gap-result-topline">
                      <span className={`gap-priority priority-${item.priority.toLowerCase()}`}>{item.priority}</span>
                      <span className="gap-rank">优先级 #{index + 1}</span>
                    </div>
                    <h3>{item.capability}</h3>
                    <div className="gap-metric-grid">
                      <div><strong>{coverage}%</strong><span>目标岗位覆盖</span></div>
                      <div><strong>{mustHaveRatio}%</strong><span>其中属于硬要求</span></div>
                      <div><strong>{item.supportingJobIds.length}</strong><span>个岗位提到</span></div>
                      <div><strong>{item.evidenceIds.length}</strong><span>条当前证据</span></div>
                    </div>

                    <div className="gap-result-section">
                      <span className="gap-result-label">为什么值得现在补</span>
                      <p>
                        这项能力出现在 {item.supportingJobIds.length} 个目标岗位中；
                        {mustHaveRatio >= 50 ? "而且较多岗位把它当作必须条件。" : "其中一部分岗位把它作为必须条件或重要偏好。"}
                      </p>
                      {supportingJobs.length > 0 ? (
                        <div className="gap-supporting-jobs">
                          {supportingJobs.map((job) => (
                            <Link href={`/jobs/${job.jobId}`} key={job.jobId}>{job.title} · {job.company}</Link>
                          ))}
                        </div>
                      ) : null}
                    </div>

                    <div className="gap-result-section">
                      <span className="gap-result-label">你现在差在哪里</span>
                      <p>{currentStateLabel(item.currentState)}</p>
                    </div>

                    <div className="gap-result-section gap-completion-section">
                      <span className="gap-result-label">做到什么算补齐</span>
                      <ol>
                        {item.completionCriteria.map((criterion) => (
                          <li key={criterion}>{completionCriterionLabel(criterion)}</li>
                        ))}
                      </ol>
                      {evidenceHref ? (
                        <div className="actions">
                          <Link className="button" href={evidenceHref}>核实并补充真实经历</Link>
                          <p className="muted">
                            只有你确实做过时才补 Skill / Evidence；保存后回到推荐页显式 Re-match，JobLens 会用这些 Requirement 重新验证这次资料是否真的带来改善。
                          </p>
                        </div>
                      ) : null}
                    </div>

                    {item.priority === "P0" && supportingJobs.length > 0 ? (
                      <div className="gap-result-section">
                        <span className="gap-result-label">针对这些岗位开始准备</span>
                        <p>直接进入受这项首要差距影响的岗位准备页，用同一组已确认 Requirement 检查简历、面试与学习清单。</p>
                        <div className="gap-supporting-jobs">
                          {supportingJobs.map((job) => (
                            <Link href={buildGapPreparationHref(item, job.jobId)} key={job.jobId}>
                              准备 {job.title} · {job.company}
                            </Link>
                          ))}
                        </div>
                      </div>
                    ) : null}

                    <details className="gap-technical-details">
                      <summary>查看技术依据</summary>
                      <dl>
                        <dt>Requirement</dt>
                        <dd>{item.supportingRequirementIds.join("、") || "无"}</dd>
                        <dt>Profile Skill</dt>
                        <dd>{item.profileSkillIds.join("、") || "无"}</dd>
                        <dt>Evidence</dt>
                        <dd>{item.evidenceIds.join("、") || "无"}</dd>
                      </dl>
                    </details>
                  </article>
                );
              })}
            </div>
          )}
        </section>
      ) : null}
    </div>
  );
}
