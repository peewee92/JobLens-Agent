"use client";

import {useRef, useState} from "react";
import type {ProfileEvalReview, ProfileEvalReviewDecision, ProfileEvalReviewPayload} from "@/lib/contracts";
import {readEvalReviewReceipt} from "@/lib/eval-review-receipt";
import {EvaluationReviewResult} from "./evaluation-review-result";
import {PendingIndicator} from "./ui/pending-indicator";

export function EvaluationReviewForm({runId, actions, send}: {
  runId: string;
  actions: {canAccept: boolean; canReject: boolean; reason: string | null};
  send: (payload: ProfileEvalReviewPayload) => Promise<Response>;
}) {
  const [reviewer, setReviewer] = useState("local-user");
  const [notes, setNotes] = useState("");
  const [pending, setPending] = useState<ProfileEvalReviewDecision | null>(null);
  const [saved, setSaved] = useState<ProfileEvalReview | null>(null);
  const [error, setError] = useState("");
  const [unknown, setUnknown] = useState(false);
  const [invalid, setInvalid] = useState<"reviewer" | "notes" | null>(null);
  const inFlight = useRef(false);
  const reviewerField = useRef<HTMLInputElement>(null);
  const notesField = useRef<HTMLTextAreaElement>(null);

  async function submit(decision: ProfileEvalReviewDecision) {
    if (inFlight.current || unknown || saved || (decision === "accepted" ? !actions.canAccept : !actions.canReject)) return;
    setInvalid(null);
    setError("");
    if (!reviewer.trim()) {
      setInvalid("reviewer");
      reviewerField.current?.focus();
      return;
    }
    if (Array.from(notes.trim()).length < 10) {
      setInvalid("notes");
      notesField.current?.focus();
      return;
    }

    inFlight.current = true;
    setPending(decision);
    try {
      const response = await send({decision, reviewer, notes});
      if (response.status >= 500 || [408, 409].includes(response.status)) {
        setUnknown(true);
      } else if (response.ok) {
        const receipt = readEvalReviewReceipt(await response.json(), runId, decision);
        if (receipt) setSaved(receipt);
        else setUnknown(true);
      } else {
        setError("未能提交审核。输入仍在，请核对填写内容和此评测是否允许人工审核。");
      }
    } catch {
      setUnknown(true);
    } finally {
      inFlight.current = false;
      setPending(null);
    }
  }

  if (saved) return <EvaluationReviewResult review={saved} announced />;
  if (!actions.canAccept && !actions.canReject) return <p className="notice">{actions.reason}</p>;

  return <div className="review-form" aria-busy={pending !== null}>
    <label>审核人
      <input ref={reviewerField} value={reviewer} readOnly={pending !== null || unknown} required
        aria-invalid={invalid === "reviewer"} aria-describedby={invalid === "reviewer" ? "eval-reviewer-error" : undefined}
        onChange={event => {setReviewer(event.target.value); if (invalid === "reviewer") setInvalid(null);}} />
    </label>
    {invalid === "reviewer" && <p className="inline-error" id="eval-reviewer-error" role="alert">请填写审核人。</p>}
    <label>审核说明
      <textarea ref={notesField} value={notes} readOnly={pending !== null || unknown} rows={5} required
        aria-invalid={invalid === "notes"} aria-describedby={invalid === "notes" ? "eval-notes-error" : "eval-notes-hint"}
        onChange={event => {setNotes(event.target.value); if (invalid === "notes") setInvalid(null);}} />
    </label>
    <p className="muted-copy" id="eval-notes-hint">请说明核对了哪些案例、为什么通过或不通过，至少 10 个字。</p>
    {invalid === "notes" && <p className="inline-error" id="eval-notes-error" role="alert">请补充至少 10 个字的审核说明。</p>}
    {actions.reason && <p className="notice">{actions.reason}</p>}
    {error && <p className="inline-error" role="alert">{error}</p>}
    {pending && <PendingIndicator label="正在保存人工审核…" slowLabel="还没收到保存回执，请不要重复提交。" />}
    {unknown ? <div className="jl-callout" data-tone="warning">
      <p role="alert">暂时不能确认审核是否已保存。当前输入仍在，请先查看已保存的结论，不要重复提交。</p>
      <a className="button-secondary" href={`./${encodeURIComponent(runId)}`} target="_blank" rel="noopener">在新标签页查看处理结果</a>
    </div> : <div className="actions">
      <button className="button" type="button" disabled={!actions.canAccept || pending !== null} onClick={() => void submit("accepted")}>
        {pending === "accepted" ? "正在保存…" : "审核通过，设为参考标准"}
      </button>
      <button className="button-ghost" type="button" disabled={!actions.canReject || pending !== null} onClick={() => void submit("rejected")}>
        {pending === "rejected" ? "正在保存…" : "记录为未通过"}
      </button>
    </div>}
  </div>;
}
