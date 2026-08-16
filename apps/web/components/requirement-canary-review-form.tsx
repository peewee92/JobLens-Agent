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
      setError("请先确认已亲自核对岗位原文、抽取结果和本次调用状态。" );
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
        <legend>提交前确认</legend>
        <div className="form-grid">
          <label>
            <input
              type="checkbox"
              checked={checkedJd}
              disabled={pending !== null}
              onChange={(event) => setCheckedJd(event.target.checked)}
            />{" "}
            我已阅读岗位原文，并与抽取结果逐条对照
          </label>
          <label>
            <input
              type="checkbox"
              checked={checkedRequirements}
              disabled={pending !== null}
              onChange={(event) => setCheckedRequirements(event.target.checked)}
            />{" "}
            我已核对抽取内容、重要程度和 JD 原文依据
          </label>
          <label>
            <input
              type="checkbox"
              checked={checkedTrace}
              disabled={pending !== null}
              onChange={(event) => setCheckedTrace(event.target.checked)}
            />{" "}
            我已确认本次调用没有技术错误（如服务失败）
          </label>
        </div>
      </fieldset>

      <label>
        判断依据
        <textarea
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          minLength={20}
          rows={6}
          required
          placeholder="简要写明检查了哪些岗位、发现了什么，以及为什么允许继续或为什么需要停止。"
        />
      </label>

      <p className="notice">
        提交后不可修改。“允许继续”只表示当前抽查没有发现必须停止的问题，不代表最终质量验收已经通过。
      </p>
      {blockReason ? <p className="muted">后端状态：{blockReason}</p> : null}
      {error ? <div className="inline-error">{error}</div> : null}

      <div className="actions">
        <button
          className="button"
          type="button"
          disabled={pending !== null || !continueAllowed}
          onClick={() => void submit("continue")}
        >
          {pending === "continue" ? "提交中…" : "允许继续"}
        </button>
        <button
          className="button-ghost"
          type="button"
          disabled={pending !== null || !stopAllowed}
          onClick={() => void submit("stop")}
        >
          {pending === "stop" ? "提交中…" : "停止这次验收"}
        </button>
      </div>
    </div>
  );
}
