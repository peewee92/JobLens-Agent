import assert from "node:assert/strict";
import test from "node:test";

import type {CareerContextReleaseReadiness} from "@/lib/contracts";
import {
  careerContextReleaseBlockerLabels,
  careerContextReleaseLabel,
} from "@/lib/career-context";

function readiness(
  releaseEligible: boolean,
): CareerContextReleaseReadiness {
  return {
    releaseEligible,
    confirmationBoundary: "explicit_versioned_user_confirmation",
    profileId: releaseEligible ? "prof_1" : null,
    profileVersion: releaseEligible ? 1 : null,
    profileCreatedAt: releaseEligible ? "2026-08-05T10:00:00Z" : null,
    profileEvidenceCount: releaseEligible ? 2 : 0,
    profileSkillCount: releaseEligible ? 2 : 0,
    searchIntentId: releaseEligible ? "intent_1" : null,
    searchIntentVersion: releaseEligible ? 1 : null,
    searchIntentCreatedAt: releaseEligible ? "2026-08-05T10:00:00Z" : null,
    searchIntentTargetRoleCount: releaseEligible ? 2 : 0,
    blockers: releaseEligible
      ? []
      : [
          {
            code: "profile_missing",
            message: "Confirm a UserProfile version.",
          },
        ],
    dbWrites: 0,
    providerCalls: 0,
    traceRunsCreated: 0,
  };
}

test("career context release labels distinguish confirmed facts from blockers", () => {
  assert.equal(
    careerContextReleaseLabel(readiness(true)),
    "个人侧事实已可供未来 Match 使用",
  );
  assert.equal(
    careerContextReleaseLabel(readiness(false)),
    "个人侧事实尚未通过 Match 输入门禁",
  );
  assert.equal(
    careerContextReleaseBlockerLabels.profile_skill_evidence_missing,
    "技能没有关联 Evidence",
  );
  assert.equal(
    careerContextReleaseBlockerLabels.search_intent_missing,
    "尚未确认求职意向版本",
  );
});
