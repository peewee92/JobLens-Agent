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
  items: GapItem[];
  blockers: string[];
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
  if (value === "missing") return "当前职业背景里还没有确认这项能力。";
  if (value === "skill_exists_without_confirmed_evidence") {
    return "你已经写过这项能力，但还缺少可核验的项目或工作证据。";
  }
  return value;
}

function completionCriterionLabel(value: string): string {
  return completionCriteriaLabels[value] ?? value;
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
          <div className="gap-empty-state">正在整理你已经表态过的岗位…</div>
        ) : candidateError ? (
          <div className="inline-error" role="alert">{candidateError}</div>
        ) : candidates && candidates.items.length === 0 ? (
          <div className="gap-empty-state gap-empty-action">
            <div>
              <strong>还没有可用于能力规划的岗位</strong>
              <p>这里会显示你已经留下“感兴趣 / 再看看”反馈的岗位。先去岗位列表查看真实岗位并完成匹配与反馈。</p>
            </div>
            <Link className="button" href="/jobs">去查看岗位</Link>
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
              <strong>当前还不能给出可靠的能力差距结论</strong>
              <p>至少有一部分岗位要求或职业事实尚未通过使用门槛。先处理下面的准备项，再回来分析。</p>
              {result.blockers.length > 0 ? <ul>{result.blockers.map((item) => <li key={item}>{item}</li>)}</ul> : null}
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
                    </div>

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
