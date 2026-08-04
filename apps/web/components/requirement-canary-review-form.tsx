"use client";

import {useRouter} from "next/navigation";
import {useState} from "react";

import type {
  ApiErrorBody,
  RequirementAcceptanceCanaryDecision,
} from "@/lib/contracts";

export function RequirementCanaryReviewForm({
  runId,
  reviewer,
  continueAllowed,
  stopAllowed,
  blockReason,
}: {
  runId: string;
  reviewer: string;
  continueAllowed: boolean;
  stopAllowed: boolean;
  blockReason: string | null;
}) {
  const router = useRouter();
  const [notes, setNotes] = useState("");
  const [checkedJd, setCheckedJd] = useState(false);
  const [checkedRequirements, setCheckedRequirements] = useState(false);
  const [checkedTrace, setCheckedTrace] = useState(false);
  const [pending, setPending] =
    useState<RequirementAcceptanceCanaryDecision | null>(null);
  const [error, setError] = useState<string | null>(null);

  const evidenceChecked = checkedJd && checkedRequirements && checkedTrace;

  async function submit(decision: RequirementAcceptanceCanaryDecision) {
    setError(null);
    if (!evidenceChecked) {
      setError("请先确认已亲自检查完整 JD、Requirements 和 Trace。" );
      return;
    }
    if (notes.trim().length < 20) {
      setError("请写至少 20 个字符的人工判断依据。" );
      return;
    }
    const allowed = decision === "continue" ? continueAllowed : stopAllowed;
    if (!allowed) {
      setError(blockReason ?? "当前 Run 状态不允许提交该决策。" );
      return;
    }

    setPending(decision);
    try {
      const response = await fetch(
        `/api/requirement-acceptance-runs/${encodeURIComponent(runId)}/canary-review`,
        {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({reviewer, decision, notes}),
        },
      );
      if (!response.ok) {
        const body = (await response.json()) as Partial<ApiErrorBody>;
        throw new Error(
          body.error?.message ?? `提交 Canary 判断失败（${response.status}）。`,
        );
      }
      router.refresh();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "提交 Canary 人工判断失败。",
      );
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="review-form">
      <fieldset>
        <legend>提交前的个人检查</legend>
        <div className="form-grid">
          <label>
            <input
              type="checkbox"
              checked={checkedJd}
              disabled={pending !== null}
              onChange={(event) => setCheckedJd(event.target.checked)}
            />{" "}
            我已逐条阅读完整 JD，不只看模型摘要
          </label>
          <label>
            <input
              type="checkbox"
              checked={checkedRequirements}
              disabled={pending !== null}
              onChange={(event) => setCheckedRequirements(event.target.checked)}
            />{" "}
            我已核对 Requirement、importance 与 evidenceSpan
          </label>
          <label>
            <input
              type="checkbox"
              checked={checkedTrace}
              disabled={pending !== null}
              onChange={(event) => setCheckedTrace(event.target.checked)}
            />{" "}
            我已检查 Trace 状态、耗时、Token 与错误
          </label>
        </div>
      </fieldset>

      <label>
        人工判断依据
        <textarea
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          minLength={20}
          rows={6}
          required
          placeholder="写明检查了哪些 Case、发现了什么、为什么允许继续或为什么必须停止。不要让 Agent 代写判断。"
        />
      </label>

      <p className="notice">
        该决策不可修改。Continue 只表示允许继续受控抽取，不表示模型已经通过质量验收。
      </p>
      {blockReason ? <p className="muted">后端状态：{blockReason}</p> : null}
      {error ? <div className="inline-error">{error}</div> : null}

      <div className="actions">
        <button
          className="button"
          type="button"
          disabled={
            pending !== null || !evidenceChecked || !continueAllowed
          }
          onClick={() => void submit("continue")}
        >
          {pending === "continue" ? "提交中…" : "Continue：允许继续受控执行"}
        </button>
        <button
          className="button-ghost"
          type="button"
          disabled={pending !== null || !evidenceChecked || !stopAllowed}
          onClick={() => void submit("stop")}
        >
          {pending === "stop" ? "提交中…" : "Stop：永久停止该 Run"}
        </button>
      </div>
    </div>
  );
}
