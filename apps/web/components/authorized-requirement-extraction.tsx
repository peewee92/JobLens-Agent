"use client";
import type {RequirementCallPlan} from "@/lib/contracts";
import {AuthorizedModelCall} from "@/components/authorized-model-call";

export function AuthorizedRequirementExtraction({jobId, plan, disabled}: {
  jobId: string; plan: RequirementCallPlan; disabled: boolean;
}) {
  return <AuthorizedModelCall jobId={jobId} plan={plan} disabled={disabled} kind="requirement" />;
}
