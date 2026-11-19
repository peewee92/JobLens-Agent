import type {ProfileEvalReview, ProfileEvalReviewDecision} from "@/lib/contracts";

export function readEvalReviewReceipt(body: unknown, runId: string, decision: ProfileEvalReviewDecision): ProfileEvalReview | null {
  if (!body || typeof body !== "object") return null;
  const review = body as Partial<ProfileEvalReview>;
  if (review.evalRunId !== runId || review.decision !== decision
    || typeof review.id !== "string" || !review.id
    || typeof review.reviewer !== "string" || !review.reviewer
    || typeof review.notes !== "string"
    || typeof review.reviewedAt !== "string" || !Number.isFinite(Date.parse(review.reviewedAt))) return null;
  return {id: review.id, evalRunId: runId, decision, reviewer: review.reviewer, notes: review.notes, reviewedAt: review.reviewedAt};
}
