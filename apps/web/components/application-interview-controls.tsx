"use client";

import {FormEvent, useRef, useState} from "react";

import type {ApplicationInterviewAnswerReview, ApplicationInterviewQuestionSet} from "@/lib/contracts";

export function ApplicationInterviewControls({workspaceId, actorId, questionSet, evidenceSummaries}: {
  workspaceId: string;
  actorId: string;
  questionSet: ApplicationInterviewQuestionSet;
  evidenceSummaries: ReadonlyMap<string, string>;
}) {
  const inFlight = useRef(false);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<{questionId: string; text: string} | null>(null);
  const [reviews, setReviews] = useState<Record<string, ApplicationInterviewAnswerReview>>({});

  async function submit(event: FormEvent<HTMLFormElement>, questionId: string) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
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
          body: JSON.stringify({
            answerText: form.get("answerText"),
            evidenceIds,
            actorId,
            idempotencyKey: `web-interview-${workspaceId}-${questionId}`,
          }),
        },
      );
      const payload = await response.json().catch(() => null) as (ApplicationInterviewAnswerReview & {detail?: string}) | null;
      if (!response.ok || !payload || payload.questionId !== questionId) throw new Error("回答审核未完成，请检查选择或刷新后再试。");
      setReviews((current) => ({...current, [questionId]: payload}));
    } catch (caught) {
      setError({questionId, text: caught instanceof TypeError ? "连接中断，暂时无法看到审核结果，请检查后重试。" : "回答审核未完成，请检查选择或刷新后再试。"});
    } finally {
      inFlight.current = false;
      setPending(null);
    }
  }

  return <div>
    {questionSet.questions.length === 0 ? <p className="muted">当前没有可练习的问题。</p> : null}
    {questionSet.questions.map((question) => {
      const review = reviews[question.questionId];
      return <form key={question.questionId} onSubmit={(event) => submit(event, question.questionId)} className="eligibility-result-card interview-practice-form">
        <strong>{question.prompt}</strong>
        <p className="muted">对应岗位要求：{question.requirementText}</p>
        <label>你的真实回答<textarea name="answerText" required rows={5} minLength={1} maxLength={12000} /></label>
        {question.allowedEvidenceIds.length > 0 ? <fieldset>
          <legend>这次回答实际使用了哪些已确认经历？</legend>
          {question.allowedEvidenceIds.map((evidenceId, index) => <div key={evidenceId}>
            <label><input type="checkbox" name="evidenceIds" value={evidenceId} /> {evidenceSummaries.get(evidenceId) ?? `已确认经历 ${index + 1}（此处无摘要，核对后再选）`}</label>
            {!evidenceSummaries.has(evidenceId) && <details><summary>查看经历引用</summary>{evidenceId}</details>}
          </div>)}
        </fieldset> : <p className="muted">这项要求当前没有可引用的已确认经历；可以练习回答，但审核不会把未确认事实当作依据。</p>}
        <div className="actions"><button className="button-secondary" disabled={pending !== null}>{pending === question.questionId ? "正在审核…" : review?.retryRecommended ? "修改后重新审核" : "按真实经历核对回答"}</button></div>
        {review ? <div className="notice" role="status" style={{marginTop: 10}}>
          <strong>{review.retryRecommended ? "建议补充真实依据后重试" : "回答中的经历引用已核对"}</strong>
          <p>{review.feedback.join("；")}</p>
          <small>核对通过 {review.acceptedEvidenceIds.length} 项经历 · 未通过 {review.rejectedEvidenceIds.length} 项</small>
        </div> : null}
        {error?.questionId === question.questionId && <p role="alert" className="error-copy">{error.text}</p>}
      </form>;
    })}
  </div>;
}
