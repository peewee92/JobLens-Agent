import type {ProfileEvalReview} from "@/lib/contracts";
import {formatDateTime} from "@/lib/format";

export function EvaluationReviewResult({review, announced = false}: {review: ProfileEvalReview; announced?: boolean}) {
  return <div className={`review-result review-${review.decision}`} role={announced ? "status" : undefined}>
    <strong>{review.decision === "accepted" ? "已通过人工审核" : "人工审核未通过"}</strong>
    <p>{review.notes}</p>
    <small>{review.reviewer} · {formatDateTime(review.reviewedAt)}</small>
  </div>;
}
