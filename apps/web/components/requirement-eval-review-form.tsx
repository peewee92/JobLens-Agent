"use client";

import type {RequirementEvalRunSummary} from "@/lib/contracts";
import {reviewActionsForRequirementRun} from "@/lib/requirement-evals";
import {EvaluationReviewForm} from "./evaluation-review-form";

export function RequirementEvalReviewForm({run, alreadyReviewed}: {
  run: RequirementEvalRunSummary;
  alreadyReviewed: boolean;
}) {
  return <EvaluationReviewForm runId={run.id} actions={reviewActionsForRequirementRun(run, alreadyReviewed)}
    send={payload => fetch(`/api/requirement-evals/${encodeURIComponent(run.id)}/review`, {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload),
    })} />;
}
