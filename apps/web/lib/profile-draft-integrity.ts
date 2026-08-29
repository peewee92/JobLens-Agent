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

export type EvidenceRenameImpact = {
  evidenceIndex: number;
  previousKey: string;
  nextKey: string;
  affectedSkillNames: string[];
};

export type EvidenceDeleteImpact = {
  evidenceIndex: number;
  evidenceKeys: string[];
  affectedSkillNames: string[];
};

export type EvidenceContentImpact = {
  evidenceIndex: number;
  evidenceKeys: string[];
  affectedSkillNames: string[];
};

export type SkillDanglingEvidenceIssue = {
  skillIndex: number;
  skillName: string;
  missingEvidenceKeys: string[];
};

export function skillDanglingEvidenceIssues({
  evidence,
  skills,
}: {
  evidence: EvidenceDraftLike[];
  skills: SkillDraftLike[];
}): SkillDanglingEvidenceIssue[] {
  const completeEvidenceKeys = new Set(
    evidence
      .filter((item) => item.key.trim() && item.summary.trim())
      .map((item) => normalized(item.key)),
  );

  return skills.flatMap((skill, skillIndex) => {
    const skillName = skill.name.trim();
    if (!skillName) return [];
    const missingEvidenceKeys = skill.evidenceKeys
      .map((key) => key.trim())
      .filter(Boolean)
      .filter((key) => !completeEvidenceKeys.has(normalized(key)));
    if (missingEvidenceKeys.length === 0) return [];
    return [{skillIndex, skillName, missingEvidenceKeys}];
  });
}

export function evidenceRenameImpacts({
  originalEvidenceKeys,
  evidence,
  skills,
}: {
  originalEvidenceKeys: string[];
  evidence: EvidenceDraftLike[];
  skills: SkillDraftLike[];
}): EvidenceRenameImpact[] {
  return evidence.flatMap((item, evidenceIndex) => {
    const previousKey = originalEvidenceKeys[evidenceIndex]?.trim() ?? "";
    const nextKey = item.key.trim();
    if (!previousKey || !nextKey || normalized(previousKey) === normalized(nextKey)) return [];

    const affectedSkillNames = skills
      .filter((skill) => skill.evidenceKeys.some((key) => normalized(key) === normalized(previousKey)))
      .map((skill) => skill.name.trim())
      .filter(Boolean);
    if (affectedSkillNames.length === 0) return [];

    return [{evidenceIndex, previousKey, nextKey, affectedSkillNames}];
  });
}

export function evidenceContentImpact({
  evidenceIndex,
  originalEvidenceKeys,
  evidence,
  skills,
}: {
  evidenceIndex: number;
  originalEvidenceKeys: string[];
  evidence: EvidenceDraftLike[];
  skills: SkillDraftLike[];
}): EvidenceContentImpact | null {
  const item = evidence[evidenceIndex];
  if (!item || item.summary.trim()) return null;

  const currentKey = item.key.trim();
  const originalKey = originalEvidenceKeys[evidenceIndex]?.trim() ?? "";
  const evidenceKeys = [currentKey, originalKey]
    .filter(Boolean)
    .filter((key, index, keys) => keys.findIndex((candidate) => normalized(candidate) === normalized(key)) === index);
  if (evidenceKeys.length === 0) return null;

  const affectedSkillNames = skills
    .filter((skill) => skill.evidenceKeys.some((key) =>
      evidenceKeys.some((evidenceKey) => normalized(evidenceKey) === normalized(key)),
    ))
    .map((skill) => skill.name.trim())
    .filter(Boolean);
  if (affectedSkillNames.length === 0) return null;

  return {evidenceIndex, evidenceKeys, affectedSkillNames};
}

export function evidenceDeleteImpact({
  evidenceIndex,
  originalEvidenceKeys,
  evidence,
  skills,
}: {
  evidenceIndex: number;
  originalEvidenceKeys: string[];
  evidence: EvidenceDraftLike[];
  skills: SkillDraftLike[];
}): EvidenceDeleteImpact | null {
  const currentKey = evidence[evidenceIndex]?.key.trim() ?? "";
  const originalKey = originalEvidenceKeys[evidenceIndex]?.trim() ?? "";
  const evidenceKeys = [currentKey, originalKey]
    .filter(Boolean)
    .filter((key, index, keys) => keys.findIndex((candidate) => normalized(candidate) === normalized(key)) === index);
  if (evidenceKeys.length === 0) return null;

  const affectedSkillNames = skills
    .filter((skill) => skill.evidenceKeys.some((key) =>
      evidenceKeys.some((evidenceKey) => normalized(evidenceKey) === normalized(key)),
    ))
    .map((skill) => skill.name.trim())
    .filter(Boolean);
  if (affectedSkillNames.length === 0) return null;

  return {evidenceIndex, evidenceKeys, affectedSkillNames};
}

export function removeEvidenceKeyReferences({
  currentEvidenceKeys,
  deletedEvidenceKeys,
}: {
  currentEvidenceKeys: string[];
  deletedEvidenceKeys: string[];
}): string[] {
  const deleted = new Set(deletedEvidenceKeys.map(normalized));
  return currentEvidenceKeys.filter((key) => !deleted.has(normalized(key)));
}

export function migrateEvidenceKeyReferences({
  currentEvidenceKeys,
  previousEvidenceKey,
  nextEvidenceKey,
}: {
  currentEvidenceKeys: string[];
  previousEvidenceKey: string;
  nextEvidenceKey: string;
}): string[] {
  const previous = previousEvidenceKey.trim();
  const next = nextEvidenceKey.trim();
  if (!previous || !next || normalized(previous) === normalized(next)) return currentEvidenceKeys;

  const migrated: string[] = [];
  for (const key of currentEvidenceKeys) {
    const candidate = normalized(key) === normalized(previous) ? next : key.trim();
    if (candidate && !migrated.some((existing) => normalized(existing) === normalized(candidate))) {
      migrated.push(candidate);
    }
  }
  return migrated;
}

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
