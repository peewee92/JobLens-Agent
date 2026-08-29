type EvidenceDraftLike = {
  key: string;
  summary: string;
};

type SkillDraftLike = {
  name: string;
  evidenceKeys: string[];
};

export type FocusedSkillEvidenceIssue =
  | {
      kind: "missing_links";
      skillName: string;
    }
  | {
      kind: "dangling_links";
      skillName: string;
      missingEvidenceKeys: string[];
    };

export function repairFocusedSkillEvidenceKeys({
  currentEvidenceKeys,
  missingEvidenceKeys,
  replacementEvidenceKey,
}: {
  currentEvidenceKeys: string[];
  missingEvidenceKeys: string[];
  replacementEvidenceKey: string;
}): string[] {
  const replacement = replacementEvidenceKey.trim();
  if (!replacement) return currentEvidenceKeys;

  const missing = new Set(missingEvidenceKeys.map(normalized));
  const repaired = currentEvidenceKeys.filter((key) => !missing.has(normalized(key)));
  if (!repaired.some((key) => normalized(key) === normalized(replacement))) {
    repaired.push(replacement);
  }
  return repaired;
}

function normalized(value: string): string {
  return value.trim().toLocaleLowerCase();
}

export function focusedSkillEvidenceIssue({
  focusCapability,
  evidence,
  skills,
}: {
  focusCapability: string | null;
  evidence: EvidenceDraftLike[];
  skills: SkillDraftLike[];
}): FocusedSkillEvidenceIssue | null {
  const capability = normalized(focusCapability ?? "");
  if (!capability) return null;

  const skill = skills.find((item) => normalized(item.name) === capability);
  if (!skill) return null;

  const evidenceByKey = new Map(
    evidence
      .filter((item) => item.key.trim() && item.summary.trim())
      .map((item) => [normalized(item.key), item]),
  );
  const linkedKeys = skill.evidenceKeys.map((key) => key.trim()).filter(Boolean);

  if (linkedKeys.length === 0) {
    return {kind: "missing_links", skillName: skill.name.trim()};
  }

  const missingEvidenceKeys = linkedKeys.filter((key) => !evidenceByKey.has(normalized(key)));
  if (missingEvidenceKeys.length > 0) {
    return {
      kind: "dangling_links",
      skillName: skill.name.trim(),
      missingEvidenceKeys,
    };
  }

  return null;
}
