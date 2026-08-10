"use client";

import {FormEvent, useState} from "react";

type GapItem = {
  capability: string;
  priority: string;
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

function parseFeedbackIds(value: string) {
  return [...new Set(value.split(/[\s,]+/).map((item) => item.trim()).filter(Boolean))];
}

export function TargetCohortGapPanel() {
  const [feedbackText, setFeedbackText] = useState("");
  const [result, setResult] = useState<GapResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const selectedFeedbackIds = parseFeedbackIds(feedbackText);
    if (selectedFeedbackIds.length === 0) {
      setError("请至少填写一个已选择的反馈 ID。");
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
          selectedFeedbackIds,
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        setError(payload?.detail?.message ?? "暂时无法生成能力差距，请检查目标岗位反馈是否仍然有效。");
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
    <section>
      <form onSubmit={submit}>
        <label htmlFor="feedback-ids">已选择岗位的反馈 ID</label>
        <textarea
          id="feedback-ids"
          rows={4}
          value={feedbackText}
          onChange={(event) => setFeedbackText(event.target.value)}
          placeholder="可用逗号、空格或换行分隔"
        />
        <p>只会分析你明确选择的岗位；不会自动把“可能感兴趣”加入目标集合。</p>
        <button type="submit" disabled={loading}>{loading ? "分析中…" : "查看能力差距"}</button>
      </form>

      {error ? <p role="alert">{error}</p> : null}

      {result ? (
        <div>
          <p>目标岗位：{result.jobIds.length} 个</p>
          {!result.factsUsable ? (
            <div>
              <strong>当前事实尚未通过使用门槛。</strong>
              {result.blockers.length > 0 ? <ul>{result.blockers.map((item) => <li key={item}>{item}</li>)}</ul> : null}
            </div>
          ) : result.items.length === 0 ? (
            <p>当前没有需要补齐的能力差距。</p>
          ) : (
            result.items.map((item) => (
              <details key={item.capability}>
                <summary>{item.priority} · {item.capability}</summary>
                <dl>
                  <dt>为什么重要</dt>
                  <dd>
                    目标岗位覆盖 {Math.round((item.whyImportant.targetCoverage ?? 0) * 100)}%，
                    其中 must-have 占 {Math.round((item.whyImportant.mustHaveRatio ?? 0) * 100)}%。
                  </dd>
                  <dt>哪些岗位要求</dt>
                  <dd>岗位：{item.supportingJobIds.join("、") || "无"}</dd>
                  <dd>Requirement：{item.supportingRequirementIds.join("、") || "无"}</dd>
                  <dt>我当前有什么证据</dt>
                  <dd>Profile Skill：{item.profileSkillIds.join("、") || "无"}</dd>
                  <dd>Evidence：{item.evidenceIds.join("、") || "无"}</dd>
                  <dt>具体缺什么</dt>
                  <dd>{item.currentState}</dd>
                  <dt>做到什么算补齐</dt>
                  <dd>
                    <ul>{item.completionCriteria.map((criterion) => <li key={criterion}>{criterion}</li>)}</ul>
                  </dd>
                </dl>
              </details>
            ))
          )}
        </div>
      ) : null}
    </section>
  );
}
