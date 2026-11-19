"use client";

import type {ProfileEvalRunSummary} from "@/lib/contracts";
import {reviewActionsForRun} from "@/lib/profile-evals";
import {EvaluationReviewForm} from "./evaluation-review-form";

export function ProfileEvalReviewForm({run, alreadyReviewed}: {
  run: ProfileEvalRunSummary;
  alreadyReviewed: boolean;
}) {
  return <EvaluationReviewForm runId={run.id} actions={reviewActionsForRun(run, alreadyReviewed)}
    send={payload => fetch(`/api/profile-evals/${encodeURIComponent(run.id)}/review`, {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload),
    })} />;
}
