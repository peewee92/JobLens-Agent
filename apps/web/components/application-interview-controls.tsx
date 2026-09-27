"use client";

import {FormEvent, useState} from "react";

import type {ApplicationInterviewAnswerReview, ApplicationInterviewQuestionSet} from "@/lib/contracts";

export function ApplicationInterviewControls({workspaceId, questionSet}: {
  workspaceId: string;
  questionSet: ApplicationInterviewQuestionSet;
}) {
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reviews, setReviews] = useState<Record<string, ApplicationInterviewAnswerReview>>({});

  async function submit(event: FormEvent<HTMLFormElement>, questionId: string) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const evidenceIds = form.getAll("evidenceIds").map(String);
    setPending(questionId);
    setError(null);
    try {
      const response = await fetch(
        `/api/application-workspaces/${encodeURIComponent(workspaceId)}/interview/questions/${encodeURIComponent(questionId)}/review`,
        {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({answerText: form.get("answerText"), evidenceIds}),
        },
      );
      const payload = await response.json().catch(() => null) as (ApplicationInterviewAnswerReview & {detail?: string}) | null;
      if (!response.ok || !payload) throw new Error(payload?.detail ?? "回答审核未完成，请稍后重试。");
      setReviews((current) => ({...current, [questionId]: payload}));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "回答审核未完成，请稍后重试。");
    } finally {
      setPending(null);
    }
  }

  return <div>
    {questionSet.questions.length === 0 ? <p className="muted">当前没有可练习的问题。</p> : null}
    {questionSet.questions.map((question) => {
      const review = reviews[question.questionId];
      return <form key={question.questionId} onSubmit={(event) => submit(event, question.questionId)} className="eligibility-result-card" style={{marginTop: 12}}>
        <strong>{question.prompt}</strong>
        <p className="muted">对应 Requirement：{question.requirementText}</p>
        <label>你的真实回答<textarea name="answerText" required minLength={1} maxLength={12000} /></label>
        {question.allowedEvidenceIds.length > 0 ? <fieldset>
          <legend>这次回答实际使用了哪些已确认 Evidence？</legend>
          {question.allowedEvidenceIds.map((evidenceId) => <label key={evidenceId} style={{display: "block"}}><input type="checkbox" name="evidenceIds" value={evidenceId} /> {evidenceId}</label>)}
        </fieldset> : <p className="muted">该 Requirement 当前没有已确认 Evidence；可以练习回答，但审核不会把未确认事实当作依据。</p>}
        <div className="actions"><button className="button-secondary" disabled={pending !== null}>{pending === question.questionId ? "正在审核…" : review?.retryRecommended ? "修改后重新审核" : "按真实 Evidence 审核回答"}</button></div>
        {review ? <div className="notice" style={{marginTop: 10}}>
          <strong>{review.retryRecommended ? "建议补充真实依据后重试" : "回答已通过 Evidence grounding 检查"}</strong>
          <p>{review.feedback.join("；")}</p>
          <small>接受 Evidence {review.acceptedEvidenceIds.length} 项 · 拒绝 {review.rejectedEvidenceIds.length} 项 · Provider calls: {review.providerCalls}</small>
        </div> : null}
      </form>;
    })}
    {error ? <p className="error-copy">{error}</p> : null}
  </div>;
}
