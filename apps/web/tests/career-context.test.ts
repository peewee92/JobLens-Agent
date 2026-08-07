import assert from "node:assert/strict";
import test from "node:test";

import type {CareerContextReleaseReadiness} from "@/lib/contracts";
import {
  careerContextReleaseBlockerCopy,
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
    "你的信息已准备好，可用于后续岗位匹配",
  );
  assert.equal(
    careerContextReleaseLabel(readiness(false)),
    "还需要补充一些信息，才能用于后续岗位匹配",
  );
  assert.equal(
    careerContextReleaseBlockerCopy("profile_skill_evidence_missing").title,
    "有技能还没有经历支撑",
  );
  assert.equal(
    careerContextReleaseBlockerCopy("search_intent_missing").title,
    "还没有保存你的求职偏好",
  );
});
