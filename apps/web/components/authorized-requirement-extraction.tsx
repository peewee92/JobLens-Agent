"use client";
import type {RequirementCallPlan} from "@/lib/contracts";
import {savedModelExtractionHref} from "@/lib/authorized-model-results";
import {AuthorizedModelCall} from "@/components/authorized-model-call";

export function AuthorizedRequirementExtraction({jobId, plan, disabled, detailHref}: {
  jobId: string; plan: RequirementCallPlan; disabled: boolean; detailHref?: string;
}) {
  return <AuthorizedModelCall jobId={jobId} plan={plan} disabled={disabled} kind="requirement"
    extractionHref={detailHref ? id => savedModelExtractionHref(detailHref, id) : undefined} />;
}
