"use client";

import {useRouter} from "next/navigation";
import {FormEvent, useMemo, useRef, useState} from "react";

import {ResumeProposalPanel} from "@/components/resume-proposal-panel";
import {
  isBlankProfileDraft,
  proposalToProfileDraft,
} from "@/lib/profile-proposal";
import {
  evidenceContentImpact,
  evidenceDeleteImpact,
  evidenceRenameImpacts,
  focusedSkillEvidenceIssue,
  migrateEvidenceKeyReferences,
  removeEvidenceKeyReferences,
  repairFocusedSkillEvidenceKeys,
  skillDanglingEvidenceIssues,
} from "@/lib/profile-draft-integrity";
import {userFacingApiError} from "@/lib/user-facing-errors";
import type {
  ApiErrorBody,
  EvidenceType,
  ProfileExtractionProposal,
  RequirementType,
  SaveProfilePayload,
  SaveSearchIntentPayload,
  SearchIntent,
  Seniority,
  SkillLevel,
  UserProfile,
} from "@/lib/contracts";

type EvidenceDraft = SaveProfilePayload["evidence"][number];
type SkillDraft = SaveProfilePayload["skills"][number];
type SaveState = {kind: "idle" | "saving" | "success" | "error"; message: string};

const EMPTY_EVIDENCE: EvidenceDraft = {
  key: "",
  type: "project",
  summary: "",
  source: "confirmed by user",
};
const EMPTY_SKILL: SkillDraft = {
  name: "",
  level: "working",
  evidenceKeys: [],
};

const evidenceTypeLabels: Record<EvidenceType, string> = {
  work: "工作经历",
  project: "项目经历",
  education: "教育经历",
  achievement: "成果",
  self_report: "本人补充",
};

const skillLevelLabels: Record<SkillLevel, string> = {
  strong: "强项",
  working: "可工作使用",
  basic: "基础了解",
  unknown: "待确认",
};

const requirementFocusCopy: Record<RequirementType, {title: string; description: string}> = {
  education: {
    title: "先补教育事实，再回到岗位优先级重算",
    description: "当前岗位存在学历、专业或院校硬条件，但已确认 Profile 还缺少足够直接的教育证据。只填写真实信息；学历层级、专业和岗位明确要求的院校限定会直接影响 Eligibility 判断。",
  },
  skill: {
    title: "补充能证明技能的真实经历",
    description: "当前岗位存在技能硬条件。请优先补充你真实做过的项目或工作经历，并在“我的技能”中把技能关联到这些 Evidence。",
  },
  experience: {
    title: "补充能证明专项经验的真实经历",
    description: "当前岗位存在经验硬条件。请填写真实工作或项目经历，尽量写清负责内容、场景和可核实结果，不要为了匹配岗位补造经历。",
  },
  responsibility: {
    title: "补充能证明职责范围的真实经历",
    description: "当前岗位存在职责硬条件。请补充你实际承担过的职责和对应项目或工作背景，只有已确认 Evidence 才会进入后续匹配。",
  },
  domain: {
    title: "补充能证明领域经验的真实经历",
    description: "当前岗位存在行业或业务领域硬条件。请补充真实项目或工作场景，说明你在哪个领域做过什么，不自动推断行业经验。",
  },
  constraint: {
    title: "核对这项岗位硬约束",
    description: "当前岗位存在其他硬约束。请只补充能够直接证明该事实的真实信息；无法证明时保持缺口，不要为了通过匹配修改事实。",
  },
};

const REVIEW_EVIDENCE_LIMIT = 6;
const REVIEW_SKILL_LIMIT = 12;

function splitList(value: string): string[] {
  return value
    .split(/[\n,，]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function lines(values: string[]): string {
  return values.join("\n");
}

async function apiMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as Partial<ApiErrorBody>;
    return userFacingApiError(body, `保存失败（${response.status}），请稍后重试。`);
  } catch {
    return `保存失败（${response.status}）。`;
  }
}

function initialEvidence(profile: UserProfile | null): EvidenceDraft[] {
  return profile?.evidence.map(({key, type, summary, source}) => ({
    key,
    type,
    summary,
    source,
  })) ?? [{...EMPTY_EVIDENCE}];
}

function initialSkills(profile: UserProfile | null): SkillDraft[] {
  if (!profile) return [{...EMPTY_SKILL}];
  const keyById = new Map(profile.evidence.map((item) => [item.id, item.key]));
  return profile.skills.map((item) => ({
    name: item.name,
    level: item.level,
    evidenceKeys: item.evidenceIds
      .map((id) => keyById.get(id))
      .filter((key): key is string => Boolean(key)),
  }));
}

export function ProfileEditor({
  initialProfile,
  initialIntent,
  afterProfileSaveHref = null,
  focusEvidenceType = null,
  focusRequirementType = null,
  focusJobId = null,
  focusCapability = null,
  focusRequirementText = null,
}: {
  initialProfile: UserProfile | null;
  initialIntent: SearchIntent | null;
  afterProfileSaveHref?: string | null;
  focusEvidenceType?: EvidenceType | null;
  focusRequirementType?: RequirementType | null;
  focusJobId?: string | null;
  focusCapability?: string | null;
  focusRequirementText?: string | null;
}) {
  const router = useRouter();
  const profileFormRef = useRef<HTMLFormElement>(null);
  const [profileVersion, setProfileVersion] = useState(initialProfile?.version ?? 0);
  const [headline, setHeadline] = useState(initialProfile?.headline ?? "");
  const [years, setYears] = useState(
    initialProfile?.yearsOfExperience?.toString() ?? "",
  );
  const [evidence, setEvidence] = useState<EvidenceDraft[]>(
    initialEvidence(initialProfile),
  );
  const [evidenceReferenceKeys, setEvidenceReferenceKeys] = useState<string[]>(
    initialProfile?.evidence.map((item) => item.key) ?? [],
  );
  const [skills, setSkills] = useState<SkillDraft[]>(initialSkills(initialProfile));
  const [profileState, setProfileState] = useState<SaveState>({
    kind: "idle",
    message: "",
  });
  const [profileDirty, setProfileDirty] = useState(false);
  const [focusedEvidenceIndex, setFocusedEvidenceIndex] = useState<number | null>(null);
  const [isProfileEditorOpen, setIsProfileEditorOpen] = useState(
    Boolean(focusEvidenceType || focusRequirementType),
  );

  const [intentVersion, setIntentVersion] = useState(initialIntent?.version ?? 0);
  const [targetRoles, setTargetRoles] = useState(
    lines(initialIntent?.targetRoles ?? []),
  );
  const [cities, setCities] = useState(lines(initialIntent?.cities ?? []));
  const [remoteAccepted, setRemoteAccepted] = useState(
    initialIntent?.remoteAccepted === null || initialIntent?.remoteAccepted === undefined
      ? ""
      : String(initialIntent.remoteAccepted),
  );
  const [minimumSalaryK, setMinimumSalaryK] = useState(
    initialIntent?.minimumSalaryK?.toString() ?? "",
  );
  const [seniority, setSeniority] = useState<Seniority | "">(
    initialIntent?.seniority ?? "",
  );
  const [employmentTypes, setEmploymentTypes] = useState(
    lines(initialIntent?.employmentTypes ?? []),
  );
  const [excludeKeywords, setExcludeKeywords] = useState(
    lines(initialIntent?.excludeKeywords ?? []),
  );
  const [hardConstraints, setHardConstraints] = useState(
    lines(initialIntent?.hardConstraints ?? []),
  );
  const [softPreferences, setSoftPreferences] = useState(
    lines(initialIntent?.softPreferences ?? []),
  );
  const [intentState, setIntentState] = useState<SaveState>({
    kind: "idle",
    message: "",
  });

  const selectableEvidence = useMemo(
    () => evidence.map((item) => item.key.trim()).filter(Boolean),
    [evidence],
  );
  const reviewEvidence = useMemo(
    () => evidence.filter((item) => item.summary.trim() || item.key.trim()),
    [evidence],
  );
  const reviewSkills = useMemo(
    () => skills.filter((item) => item.name.trim()),
    [skills],
  );
  const focusedEvidenceCount = useMemo(
    () => focusEvidenceType
      ? evidence.filter((item) => item.type === focusEvidenceType && item.summary.trim()).length
      : 0,
    [evidence, focusEvidenceType],
  );
  const focusCapabilityCoverage = useMemo(() => {
    const normalizedCapability = focusCapability?.trim().toLocaleLowerCase();
    if (!normalizedCapability) return null;

    const matchingSkills = skills.filter(
      (item) => item.name.trim().toLocaleLowerCase() === normalizedCapability,
    );
    const linkedEvidenceKeys = new Set(
      matchingSkills.flatMap((item) => item.evidenceKeys.map((key) => key.trim()).filter(Boolean)),
    );
    const linkedEvidence = evidence.filter(
      (item) => linkedEvidenceKeys.has(item.key.trim()) && item.summary.trim(),
    );
    const status = linkedEvidence.length > 0
      ? "direct_evidence"
      : matchingSkills.length > 0
        ? "skill_only"
        : "no_exact_fact";

    return {matchingSkills, linkedEvidence, status};
  }, [evidence, focusCapability, skills]);
  const focusedEvidenceDraft = focusedEvidenceIndex === null
    ? null
    : evidence[focusedEvidenceIndex] ?? null;
  const focusedExactSkillIndex = useMemo(() => {
    const normalizedCapability = focusCapability?.trim().toLocaleLowerCase();
    if (!normalizedCapability) return -1;
    return skills.findIndex(
      (item) => item.name.trim().toLocaleLowerCase() === normalizedCapability,
    );
  }, [focusCapability, skills]);
  const canLinkFocusedEvidenceToExistingSkill = Boolean(
    focusedEvidenceDraft?.key.trim()
      && focusedEvidenceDraft.summary.trim()
      && focusedExactSkillIndex >= 0
      && !skills[focusedExactSkillIndex].evidenceKeys.includes(focusedEvidenceDraft.key.trim()),
  );
  const activeRequirementFocus = focusRequirementType
    ?? (focusEvidenceType === "education" ? "education" : null);
  const canCreateFocusedSkillFromEvidence = Boolean(
    activeRequirementFocus === "skill"
      && focusCapability?.trim()
      && focusedEvidenceDraft?.key.trim()
      && focusedEvidenceDraft.summary.trim()
      && focusedExactSkillIndex < 0,
  );
  const renameImpacts = useMemo(
    () => evidenceRenameImpacts({originalEvidenceKeys: evidenceReferenceKeys, evidence, skills}),
    [evidence, evidenceReferenceKeys, skills],
  );
  const renameImpactByEvidenceIndex = useMemo(
    () => new Map(renameImpacts.map((impact) => [impact.evidenceIndex, impact])),
    [renameImpacts],
  );
  const contentImpactByEvidenceIndex = useMemo(() => new Map(
    evidence.flatMap((_, evidenceIndex) => {
      const impact = evidenceContentImpact({
        evidenceIndex,
        originalEvidenceKeys: evidenceReferenceKeys,
        evidence,
        skills,
      });
      return impact ? [[evidenceIndex, impact] as const] : [];
    }),
  ), [evidence, evidenceReferenceKeys, skills]);
  const deleteImpactByEvidenceIndex = useMemo(() => new Map(
    evidence.flatMap((_, evidenceIndex) => {
      const impact = evidenceDeleteImpact({
        evidenceIndex,
        originalEvidenceKeys: evidenceReferenceKeys,
        evidence,
        skills,
      });
      return impact ? [[evidenceIndex, impact] as const] : [];
    }),
  ), [evidence, evidenceReferenceKeys, skills]);
  const focusedSkillIntegrityIssue = activeRequirementFocus === "skill"
    ? focusedSkillEvidenceIssue({focusCapability, evidence, skills})
    : null;
  const globalDanglingEvidenceIssues = useMemo(
    () => skillDanglingEvidenceIssues({evidence, skills}),
    [evidence, skills],
  );
  const canRepairFocusedSkillWithCurrentEvidence = Boolean(
    focusedSkillIntegrityIssue
      && focusedExactSkillIndex >= 0
      && focusedEvidenceDraft?.key.trim()
      && focusedEvidenceDraft.summary.trim(),
  );
  const profileDraftBlank = isBlankProfileDraft({headline, years, evidence, skills});
  const profileStatusLabel = profileDraftBlank
    ? "尚未填写"
    : profileDirty || profileVersion === 0
      ? "待你确认"
      : "已保存";

  function markProfileDirty() {
    setProfileDirty(true);
    if (profileState.kind === "success") {
      setProfileState({kind: "idle", message: ""});
    }
  }

  function updateEvidence(index: number, patch: Partial<EvidenceDraft>) {
    markProfileDirty();
    setEvidence((items) =>
      items.map((item, itemIndex) =>
        itemIndex === index ? {...item, ...patch} : item,
      ),
    );
  }

  function revealEvidenceEditor(index: number) {
    setFocusedEvidenceIndex(index);
    setIsProfileEditorOpen(true);
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const card = document.getElementById(`profile-evidence-card-${index}`);
        card?.scrollIntoView({behavior: "smooth", block: "center"});
        document.getElementById(`evidence-key-${index}`)?.focus({preventScroll: true});
      });
    });
  }

  function addEvidenceForCurrentRequirement(type: EvidenceType) {
    markProfileDirty();
    const blankIndex = evidence.findIndex(
      (item) => !item.key.trim() && !item.summary.trim(),
    );
    const targetIndex = blankIndex >= 0 ? blankIndex : evidence.length;
    setEvidence((items) =>
      blankIndex >= 0
        ? items.map((item, index) =>
          index === blankIndex ? {...item, type} : item,
        )
        : [...items, {...EMPTY_EVIDENCE, type}],
    );
    if (blankIndex < 0) {
      setEvidenceReferenceKeys((keys) => [...keys, ""]);
    }
    revealEvidenceEditor(targetIndex);
  }

  function linkFocusedEvidenceToExistingSkill() {
    if (!focusedEvidenceDraft || focusedExactSkillIndex < 0) return;
    const evidenceKey = focusedEvidenceDraft.key.trim();
    if (!evidenceKey || !focusedEvidenceDraft.summary.trim()) return;
    const current = skills[focusedExactSkillIndex].evidenceKeys;
    if (current.includes(evidenceKey)) return;
    updateSkill(focusedExactSkillIndex, {evidenceKeys: [...current, evidenceKey]});
  }

  function createFocusedSkillAndLinkEvidence() {
    if (!canCreateFocusedSkillFromEvidence || !focusedEvidenceDraft || !focusCapability) return;
    const evidenceKey = focusedEvidenceDraft.key.trim();
    const capability = focusCapability.trim();
    if (!evidenceKey || !capability) return;

    markProfileDirty();
    setSkills((items) => {
      const reusableBlankIndex = items.findIndex(
        (item) => !item.name.trim() && item.evidenceKeys.length === 0,
      );
      const confirmedSkill: SkillDraft = {
        name: capability,
        level: "unknown",
        evidenceKeys: [evidenceKey],
      };
      return reusableBlankIndex >= 0
        ? items.map((item, index) => index === reusableBlankIndex ? confirmedSkill : item)
        : [...items, confirmedSkill];
    });
  }

  function repairFocusedSkillWithCurrentEvidence() {
    if (
      !canRepairFocusedSkillWithCurrentEvidence
      || !focusedSkillIntegrityIssue
      || !focusedEvidenceDraft
      || focusedExactSkillIndex < 0
    ) return;

    const currentKeys = skills[focusedExactSkillIndex].evidenceKeys;
    const missingKeys = focusedSkillIntegrityIssue.kind === "dangling_links"
      ? focusedSkillIntegrityIssue.missingEvidenceKeys
      : [];
    updateSkill(focusedExactSkillIndex, {
      evidenceKeys: repairFocusedSkillEvidenceKeys({
        currentEvidenceKeys: currentKeys,
        missingEvidenceKeys: missingKeys,
        replacementEvidenceKey: focusedEvidenceDraft.key,
      }),
    });
  }

  function migrateRenamedEvidenceReferences(evidenceIndex: number) {
    const impact = renameImpactByEvidenceIndex.get(evidenceIndex);
    if (!impact) return;

    markProfileDirty();
    setSkills((items) => items.map((skill) => ({
      ...skill,
      evidenceKeys: migrateEvidenceKeyReferences({
        currentEvidenceKeys: skill.evidenceKeys,
        previousEvidenceKey: impact.previousKey,
        nextEvidenceKey: impact.nextKey,
      }),
    })));
    setEvidenceReferenceKeys((keys) => keys.map(
      (key, index) => index === evidenceIndex ? impact.nextKey : key,
    ));
  }

  function detachEmptyEvidenceReferences(evidenceIndex: number) {
    const impact = contentImpactByEvidenceIndex.get(evidenceIndex);
    if (!impact) return;
    markProfileDirty();
    setSkills((items) => items.map((skill) => ({
      ...skill,
      evidenceKeys: removeEvidenceKeyReferences({
        currentEvidenceKeys: skill.evidenceKeys,
        deletedEvidenceKeys: impact.evidenceKeys,
      }),
    })));
  }

  function deleteEvidenceAndRemoveReferences(evidenceIndex: number) {
    const impact = deleteImpactByEvidenceIndex.get(evidenceIndex);
    markProfileDirty();
    if (impact) {
      setSkills((items) => items.map((skill) => ({
        ...skill,
        evidenceKeys: removeEvidenceKeyReferences({
          currentEvidenceKeys: skill.evidenceKeys,
          deletedEvidenceKeys: impact.evidenceKeys,
        }),
      })));
    }
    setEvidence((items) => items.filter((_, index) => index !== evidenceIndex));
    setEvidenceReferenceKeys((keys) => keys.filter((_, index) => index !== evidenceIndex));
    if (focusedEvidenceIndex === evidenceIndex) setFocusedEvidenceIndex(null);
    else if (focusedEvidenceIndex !== null && focusedEvidenceIndex > evidenceIndex) {
      setFocusedEvidenceIndex(focusedEvidenceIndex - 1);
    }
  }

  function updateSkill(index: number, patch: Partial<SkillDraft>) {
    markProfileDirty();
    setSkills((items) =>
      items.map((item, itemIndex) =>
        itemIndex === index ? {...item, ...patch} : item,
      ),
    );
  }

  function toggleSkillEvidence(skillIndex: number, key: string) {
    const current = skills[skillIndex]?.evidenceKeys ?? [];
    updateSkill(skillIndex, {
      evidenceKeys: current.includes(key)
        ? current.filter((item) => item !== key)
        : [...current, key],
    });
  }

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (renameImpacts.length > 0) {
      setIsProfileEditorOpen(true);
      setProfileState({
        kind: "error",
        message: "有经历简称已改名，但已有技能仍引用旧简称。请先迁移这些既有引用，或手动取消旧关联后再保存。",
      });
      focusProfileDraft();
      return;
    }
    if (globalDanglingEvidenceIssues.length > 0) {
      setIsProfileEditorOpen(true);
      setProfileState({
        kind: "error",
        message: `有 ${globalDanglingEvidenceIssues.length} 项技能仍引用已改名、删除或未填写完整的经历：${globalDanglingEvidenceIssues.map((issue) => `${issue.skillName}（${issue.missingEvidenceKeys.join("、")}）`).join("；")}。请先重新选择真实 Evidence 后再保存，或手动移除这些失效引用。`,
      });
      focusProfileDraft();
      return;
    }
    if (focusedSkillIntegrityIssue) {
      setIsProfileEditorOpen(true);
      setProfileState({
        kind: "error",
        message: `“${focusedSkillIntegrityIssue.skillName}”当前没有真实 Evidence 支撑。请重新关联一段已填写完整的经历，或删除这项尚未确认的技能。`,
      });
      focusProfileDraft();
      return;
    }
    setProfileState({kind: "saving", message: "正在保存你的职业背景…"});
    const payload: SaveProfilePayload = {
      expectedVersion: profileVersion,
      headline,
      yearsOfExperience: years.trim() ? Number(years) : null,
      evidence,
      skills,
    };

    try {
      const response = await fetch("/api/profile", {
        method: "PUT",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        setProfileState({kind: "error", message: await apiMessage(response)});
        return;
      }
      const saved = (await response.json()) as UserProfile;
      setProfileVersion(saved.version);
      setEvidenceReferenceKeys(saved.evidence.map((item) => item.key));
      setProfileDirty(false);
      setIsProfileEditorOpen(false);
      setProfileState({
        kind: "success",
        message: afterProfileSaveHref
          ? "职业背景已保存，正在返回岗位优先级。"
          : "职业背景已保存。后续匹配会使用这份你确认过的信息。",
      });
      if (afterProfileSaveHref) {
        router.push(afterProfileSaveHref);
      } else {
        router.refresh();
      }
    } catch {
      setProfileState({kind: "error", message: "保存失败，请稍后重试。"});
    }
  }

  function currentProfileDraft() {
    return {headline, years, evidence, skills};
  }

  function applyProposal(
    proposal: ProfileExtractionProposal,
    mode: "auto" | "replace" = "replace",
  ) {
    const draft = proposalToProfileDraft(proposal);
    setHeadline(draft.headline);
    setYears(draft.years);
    setEvidence(draft.evidence);
    setEvidenceReferenceKeys(draft.evidence.map((item) => item.key));
    setSkills(draft.skills);
    setProfileDirty(true);
    setIsProfileEditorOpen(false);
    setProfileState({
      kind: "idle",
      message:
        mode === "auto"
          ? "AI 已根据简历填好职业背景草稿。请检查内容，确认无误后保存。"
          : "已用这份 AI 草稿替换当前编辑内容。请检查后保存。",
    });
  }

  function handleProposalReady(proposal: ProfileExtractionProposal): boolean {
    if (profileVersion !== 0 || !isBlankProfileDraft(currentProfileDraft())) {
      return false;
    }
    applyProposal(proposal, "auto");
    return true;
  }

  function focusProfileDraft() {
    profileFormRef.current?.scrollIntoView({behavior: "smooth", block: "start"});
  }

  function focusSkillEditor(skillIndex: number) {
    setIsProfileEditorOpen(true);
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        document.getElementById(`profile-skill-${skillIndex}`)?.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
      });
    });
  }

  function removeDanglingEvidenceReferences(skillIndex: number, missingEvidenceKeys: string[]) {
    const skill = skills[skillIndex];
    if (!skill || missingEvidenceKeys.length === 0) return;
    updateSkill(skillIndex, {
      evidenceKeys: removeEvidenceKeyReferences({
        currentEvidenceKeys: skill.evidenceKeys,
        deletedEvidenceKeys: missingEvidenceKeys,
      }),
    });
  }

  function handleProfileSubmit(event: FormEvent<HTMLFormElement>) {
    if (isProfileEditorOpen) {
      event.preventDefault();
      setIsProfileEditorOpen(false);
      focusProfileDraft();
      return;
    }
    void saveProfile(event);
  }

  async function saveIntent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIntentState({kind: "saving", message: "正在保存求职偏好…"});
    const payload: SaveSearchIntentPayload = {
      expectedVersion: intentVersion,
      targetRoles: splitList(targetRoles),
      cities: splitList(cities),
      remoteAccepted:
        remoteAccepted === "" ? null : remoteAccepted === "true",
      minimumSalaryK: minimumSalaryK.trim() ? Number(minimumSalaryK) : null,
      seniority: seniority || null,
      employmentTypes: splitList(employmentTypes),
      excludeKeywords: splitList(excludeKeywords),
      hardConstraints: splitList(hardConstraints),
      softPreferences: splitList(softPreferences),
    };

    try {
      const response = await fetch("/api/search-intent", {
        method: "PUT",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        setIntentState({kind: "error", message: await apiMessage(response)});
        return;
      }
      const saved = (await response.json()) as SearchIntent;
      setIntentVersion(saved.version);
      setIntentState({
        kind: "success",
        message: "求职偏好已保存。"
      });
      router.refresh();
    } catch {
      setIntentState({kind: "error", message: "保存失败，请稍后重试。"});
    }
  }

  return (
    <div className="profile-layout">
      <ResumeProposalPanel
        onProposalReady={handleProposalReady}
        onApply={(proposal) => applyProposal(proposal, "replace")}
        onReviewDraft={focusProfileDraft}
      />
      <form
        id="profile-background"
        ref={profileFormRef}
        className="panel profile-form"
        onSubmit={handleProfileSubmit}
      >
        <div className="section-title-row">
          <div>
            <p className="eyebrow">AI 对我的理解</p>
            <h2>我的职业背景</h2>
            <p className="section-support-copy">
              先快速确认 JobLens 对你的理解是否准确；只有发现问题时，才需要展开详细编辑。
            </p>
          </div>
          <span className={`version-badge${profileDirty ? " profile-status-dirty" : ""}`}>
            {profileStatusLabel}
          </span>
        </div>

        {activeRequirementFocus ? (
          <section className="notice" id="profile-evidence-focus">
            <strong>{requirementFocusCopy[activeRequirementFocus].title}</strong>
            <p>{requirementFocusCopy[activeRequirementFocus].description}</p>
            {focusCapability ? (
              <p className="focus-capability-note">
                当前重点核实：<strong>{focusCapability}</strong>。只补你真实做过、能被现有经历证明的内容。
              </p>
            ) : null}
            {focusRequirementText ? (
              <div className="readiness-blocker-item focus-requirement-context">
                <strong>当前岗位要求</strong>
                <p>{focusRequirementText}</p>
                <p className="muted">这段文字来自已分析的岗位要求，仅用于核对你的真实经历，不会自动写入 Profile。</p>
              </div>
            ) : null}
            {focusCapabilityCoverage ? (
              <div className="readiness-blocker-item focus-capability-coverage">
                <strong>
                  {focusCapabilityCoverage.status === "direct_evidence"
                    ? "核对状态：已有直接 Evidence"
                    : focusCapabilityCoverage.status === "skill_only"
                      ? "核对状态：只有技能名，证据还不足"
                      : "核对状态：当前没有精确事实"}
                </strong>
                {focusCapabilityCoverage.status === "direct_evidence" ? (
                  <>
                    <p>
                      已找到同名技能“{focusCapabilityCoverage.matchingSkills[0].name}”，并关联 {focusCapabilityCoverage.linkedEvidence.length} 条已确认经历。先核对这些经历是否真的能证明岗位要求；如果可以，不必重复新增。
                    </p>
                    <ul>
                      {focusCapabilityCoverage.linkedEvidence.slice(0, 3).map((item) => (
                        <li key={item.key}>{item.summary}</li>
                      ))}
                    </ul>
                    <p className="muted">下一步：确认现有 Evidence 足够准确后直接保存并回到岗位优先级重算；只有事实不完整时才补充。</p>
                  </>
                ) : focusCapabilityCoverage.status === "skill_only" ? (
                  <p>
                    已找到同名技能“{focusCapabilityCoverage.matchingSkills[0].name}”，但还没有关联已确认经历。下一步：如果你确实做过，优先把现有真实经历关联到这项技能；没有对应经历就保留缺口。
                  </p>
                ) : (
                  <p>
                    当前 Profile 里还没有同名的“{focusCapability}”技能记录。下一步：只有你确实做过时才补真实 Skill / Evidence；否则保留缺口。这里不会根据相似词自动推断你具备这项能力。
                  </p>
                )}
              </div>
            ) : null}
            {focusedSkillIntegrityIssue ? (
              <div className="review-result review-pending" role="alert">
                <strong>保存前需要修复当前技能的 Evidence 关联</strong>
                <p>
                  {focusedSkillIntegrityIssue.kind === "dangling_links"
                    ? `“${focusedSkillIntegrityIssue.skillName}”还引用了已改名、删除或未填写完整的经历：${focusedSkillIntegrityIssue.missingEvidenceKeys.join("、")}。请重新选择真实经历；JobLens 不会静默改写关联。`
                    : `“${focusedSkillIntegrityIssue.skillName}”现在没有真实 Evidence 支撑。请重新关联一段已填写完整的经历，或删除这项尚未确认的技能。`}
                </p>
                {canRepairFocusedSkillWithCurrentEvidence && focusedEvidenceDraft ? (
                  <>
                    <button className="button-secondary" type="button" onClick={repairFocusedSkillWithCurrentEvidence}>
                      用当前真实经历“{focusedEvidenceDraft.key.trim()}”修复关联
                    </button>
                    <p className="muted">只会移除已确认失效的旧引用，并保留其他仍有效的 Evidence。点击表示你确认当前这段经历确实能证明该技能；不会自动创建新能力。</p>
                  </>
                ) : null}
              </div>
            ) : null}
            {focusJobId ? (
              <p className="muted">
                保存后会回到优先投递页，并优先重新计算你正在处理的这个岗位，再处理其余已准备好的岗位。
              </p>
            ) : null}
            {activeRequirementFocus === "education" ? (
              <>
                <p className="muted">
                  {focusedEvidenceCount > 0
                    ? `当前草稿里已有 ${focusedEvidenceCount} 条教育经历，请检查关键信息是否写完整。`
                    : "当前草稿还没有完整的教育经历条目。"}
                </p>
                <div className="actions">
                  <button className="button-secondary" type="button" onClick={() => addEvidenceForCurrentRequirement("education")}>
                    + 添加教育经历
                  </button>
                </div>
              </>
            ) : (
              <>
                <p className="muted">如果现有经历还不能证明这项要求，可以直接新建一条空白 Evidence。JobLens 只帮你把录入入口放到当前任务旁边，不会替你预填能力或经历事实。</p>
                <div className="actions">
                  <button className="button-secondary" type="button" onClick={() => addEvidenceForCurrentRequirement("project")}>
                    + 添加项目经历
                  </button>
                  <button className="button-secondary" type="button" onClick={() => addEvidenceForCurrentRequirement("work")}>
                    + 添加工作经历
                  </button>
                </div>
                <p className="muted">详细编辑已为你展开；填写真实的项目、职责和结果后保存，再回到岗位优先级验证这条 Evidence 是否真的改变匹配结果。</p>
                {focusedEvidenceDraft && focusCapability ? (
                  <div className="readiness-blocker-item focus-evidence-link-helper">
                    <strong>把这条新经历连接到当前技能</strong>
                    {focusedExactSkillIndex >= 0 ? (
                      canLinkFocusedEvidenceToExistingSkill ? (
                        <>
                          <p>
                            已找到 Profile 里的精确同名技能“{skills[focusedExactSkillIndex].name}”。确认这条经历确实能证明该技能后，再显式建立关联；JobLens 不会自动替你关联。
                          </p>
                          <button className="button-secondary" type="button" onClick={linkFocusedEvidenceToExistingSkill}>
                            将这条真实经历关联到“{skills[focusedExactSkillIndex].name}”
                          </button>
                        </>
                      ) : (
                        <p>
                          {focusedEvidenceDraft.key.trim() && focusedEvidenceDraft.summary.trim()
                            ? `这条经历已经关联到“${skills[focusedExactSkillIndex].name}”，保存后再用 Re-match 验证是否真的支撑当前岗位要求。`
                            : "先填写这段经历的简称和真实内容；填写完整后，才可以把它显式关联到现有同名技能。"}
                        </p>
                      )
                    ) : activeRequirementFocus === "skill" ? (
                      canCreateFocusedSkillFromEvidence ? (
                        <>
                          <p>
                            当前 Profile 没有精确同名技能“{focusCapability}”。只有你确认自己确实具备这项技能、且刚填写的经历能证明它时，才可以由你显式创建；JobLens 不会因为岗位要求自动替你声明能力。
                          </p>
                          <button className="button-secondary" type="button" onClick={createFocusedSkillAndLinkEvidence}>
                            我确认具备“{focusCapability}”，新增技能并关联这条经历
                          </button>
                          <p className="muted">新技能会以“待确认”熟练度加入草稿，你仍可在“我的技能”中检查或调整；最终是否支撑当前 Requirement 只以保存后的 Re-match 为准。</p>
                        </>
                      ) : (
                        <p>
                          当前 Profile 没有精确同名技能“{focusCapability}”。先填写这段经历的简称和真实内容；只有你确认确实具备该技能时，才会出现显式创建入口，否则保留缺口。
                        </p>
                      )
                    ) : (
                      <p>
                        当前 Profile 没有精确同名技能“{focusCapability}”。本轮不会根据岗位要求自动创建 Skill；如果你确实具备相关能力，请在“我的技能”中基于真实经历自行补充，否则保留缺口。
                      </p>
                    )}
                  </div>
                ) : null}
              </>
            )}
          </section>
        ) : null}

        {profileDraftBlank ? (
          <section className="profile-review-empty">
            <div>
              <h3>还没有可确认的职业背景</h3>
              <p>
                推荐先用上方“AI 简历整理”自动生成草稿；如果暂时没有简历，也可以手动填写。
              </p>
            </div>
            <button
              className="button-secondary"
              type="button"
              onClick={() => setIsProfileEditorOpen(true)}
            >
              手动填写
            </button>
          </section>
        ) : (
          <div className="profile-review">
            <section className="profile-review-hero">
              <div>
                <span className="review-label">职业定位</span>
                <h3>{headline || "职业定位待补充"}</h3>
                <p>
                  {years.trim() ? `${years} 年工作经验` : "工作年限待确认"}
                  {reviewEvidence.length ? ` · ${reviewEvidence.length} 条真实经历` : ""}
                  {reviewSkills.length ? ` · ${reviewSkills.length} 项技能` : ""}
                </p>
              </div>
            </section>

            <section className="profile-review-section">
              <div className="profile-review-heading">
                <div>
                  <span className="review-label">代表经历</span>
                  <h3>这些是系统理解到的真实经历</h3>
                </div>
                <span className="review-count">{reviewEvidence.length} 条</span>
              </div>
              <div className="profile-review-card-grid">
                {reviewEvidence.slice(0, REVIEW_EVIDENCE_LIMIT).map((item, index) => (
                  <article className="profile-review-card" key={`${item.key}-${index}`}>
                    <span className="tag">{evidenceTypeLabels[item.type]}</span>
                    <p>{item.summary || "这段经历还需要补充说明"}</p>
                  </article>
                ))}
              </div>
              {reviewEvidence.length > REVIEW_EVIDENCE_LIMIT ? (
                <details className="profile-review-more">
                  <summary>查看其余 {reviewEvidence.length - REVIEW_EVIDENCE_LIMIT} 条经历</summary>
                  <div className="profile-review-card-grid">
                    {reviewEvidence.slice(REVIEW_EVIDENCE_LIMIT).map((item, index) => (
                      <article className="profile-review-card" key={`${item.key}-more-${index}`}>
                        <span className="tag">{evidenceTypeLabels[item.type]}</span>
                        <p>{item.summary}</p>
                      </article>
                    ))}
                  </div>
                </details>
              ) : null}
            </section>

            <section className="profile-review-section">
              <div className="profile-review-heading">
                <div>
                  <span className="review-label">核心技能</span>
                  <h3>这些能力会用于后续岗位匹配</h3>
                </div>
                <span className="review-count">{reviewSkills.length} 项</span>
              </div>
              <div className="profile-skill-cloud">
                {reviewSkills.slice(0, REVIEW_SKILL_LIMIT).map((item) => (
                  <span className="profile-skill-chip" key={item.name}>
                    <strong>{item.name}</strong>
                    <small>{skillLevelLabels[item.level]}</small>
                  </span>
                ))}
              </div>
              {reviewSkills.length > REVIEW_SKILL_LIMIT ? (
                <details className="profile-review-more">
                  <summary>查看其余 {reviewSkills.length - REVIEW_SKILL_LIMIT} 项技能</summary>
                  <div className="profile-skill-cloud">
                    {reviewSkills.slice(REVIEW_SKILL_LIMIT).map((item) => (
                      <span className="profile-skill-chip" key={item.name}>
                        <strong>{item.name}</strong>
                        <small>{skillLevelLabels[item.level]}</small>
                      </span>
                    ))}
                  </div>
                </details>
              ) : null}
            </section>

            <div className="profile-review-check">
              <strong>确认前重点看 3 件事</strong>
              <span>职业定位是否像你 · 经历是否确实做过 · 技能是否有真实经历支撑</span>
            </div>

            {globalDanglingEvidenceIssues.length > 0 ? (
              <div className="review-result review-pending" role="alert">
                <strong>有技能引用了已经失效的 Evidence，暂不保存</strong>
                <p>先打开详细编辑修复这些既有事实关联；JobLens 不会静默删除引用，也不会替你补造经历。</p>
                <ul>
                  {globalDanglingEvidenceIssues.map((issue) => (
                    <li key={`${issue.skillIndex}-${issue.skillName}`}>
                      <strong>{issue.skillName}</strong>：{issue.missingEvidenceKeys.join("、")}
                      <div className="actions">
                        <button
                          className="button-secondary"
                          type="button"
                          onClick={() => focusSkillEditor(issue.skillIndex)}
                        >
                          定位到这项技能
                        </button>
                        <button
                          className="button-secondary"
                          type="button"
                          onClick={() => removeDanglingEvidenceReferences(
                            issue.skillIndex,
                            issue.missingEvidenceKeys,
                          )}
                        >
                          只移除这些失效引用
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {focusedSkillIntegrityIssue?.kind === "missing_links" ? (
              <div className="review-result review-pending" role="alert">
                <strong>当前 Evidence 关联还没完整，暂不保存</strong>
                <p>“{focusedSkillIntegrityIssue.skillName}”没有任何真实经历支撑。先补关联或删除这项尚未确认的技能，再回来确认保存。</p>
              </div>
            ) : null}

            <div className="actions profile-review-actions">
              {profileDirty || profileVersion === 0 ? (
                <button className="button" type="submit" disabled={profileState.kind === "saving"}>
                  {profileState.kind === "saving" ? "正在保存…" : "内容没问题，确认保存"}
                </button>
              ) : (
                <span className="profile-saved-copy">这份职业背景已经确认并保存。</span>
              )}
              <button
                className="button-secondary"
                type="button"
                onClick={() => setIsProfileEditorOpen(true)}
              >
                {profileDirty || profileVersion === 0 ? "有问题，编辑详情" : "编辑职业背景"}
              </button>
            </div>
          </div>
        )}

        {isProfileEditorOpen ? (
          <section className="profile-detail-editor" aria-label="职业背景详细编辑">
            <div className="profile-detail-editor-heading">
              <div>
                <span className="review-label">详细编辑</span>
                <h3>修改不准确或遗漏的内容</h3>
                <p>这里只在需要时使用。修改完成后先返回卡片审核，再确认保存。</p>
              </div>
              <button
                className="button-secondary"
                type="button"
                onClick={() => {
                  setIsProfileEditorOpen(false);
                  focusProfileDraft();
                }}
              >
                完成编辑，返回审核
              </button>
            </div>

        <div className="profile-grid">
          <div className="field profile-span-2">
            <label htmlFor="headline">职业定位</label>
            <input
              id="headline"
              value={headline}
              onChange={(event) => {
                setHeadline(event.target.value);
                markProfileDirty();
              }}
              placeholder="例如：8 年前端经验，正在转向 AI 应用工程"
              required
            />
          </div>
          <div className="field">
            <label htmlFor="years">工作年限</label>
            <input
              id="years"
              type="number"
              min="0"
              step="0.5"
              value={years}
              onChange={(event) => {
                setYears(event.target.value);
                markProfileDirty();
              }}
              placeholder="8"
            />
          </div>
        </div>

        <div className="subsection-heading" id="profile-evidence">
          <div>
            <h3>经历与成果</h3>
            <p>记录真正做过的工作、项目、教育和成果，后面的技能需要从这些经历中找到依据。</p>
          </div>
          <button
            className="button-secondary"
            type="button"
            onClick={() => {
              markProfileDirty();
              setEvidence((items) => [...items, {...EMPTY_EVIDENCE}]);
              setEvidenceReferenceKeys((keys) => [...keys, ""]);
            }}
          >
            + 添加经历
          </button>
        </div>

        <div className="editor-list">
          {evidence.map((item, index) => (
            <article
              className="editor-card"
              id={`profile-evidence-card-${index}`}
              key={`evidence-${index}`}
            >
              <div className="editor-card-grid">
                <div className="field">
                  <label htmlFor={`evidence-key-${index}`}>这段经历的简称</label>
                  <input
                    id={`evidence-key-${index}`}
                    value={item.key}
                    onChange={(event) => updateEvidence(index, {key: event.target.value})}
                    placeholder="例如：JobLens 项目"
                    required
                  />
                </div>
                <div className="field">
                  <label htmlFor={`evidence-type-${index}`}>类型</label>
                  <select
                    id={`evidence-type-${index}`}
                    value={item.type}
                    onChange={(event) =>
                      updateEvidence(index, {type: event.target.value as EvidenceType})
                    }
                  >
                    <option value="work">工作</option>
                    <option value="project">项目</option>
                    <option value="education">教育</option>
                    <option value="achievement">成果</option>
                    <option value="self_report">自述</option>
                  </select>
                </div>
                <div className="field profile-span-2">
                  <label htmlFor={`evidence-summary-${index}`}>我做了什么</label>
                  <textarea
                    id={`evidence-summary-${index}`}
                    value={item.summary}
                    onChange={(event) =>
                      updateEvidence(index, {summary: event.target.value})
                    }
                    placeholder="做过什么、在哪个项目、产生了什么结果"
                    required
                  />
                </div>
                <details className="technical-details profile-span-2">
                  <summary>查看来源记录</summary>
                  <div className="field">
                    <label htmlFor={`evidence-source-${index}`}>来源记录（用于后续核对）</label>
                    <input
                      id={`evidence-source-${index}`}
                      value={item.source}
                      onChange={(event) =>
                        updateEvidence(index, {source: event.target.value})
                      }
                      placeholder="例如：本人确认、简历、项目记录"
                      required
                    />
                  </div>
                </details>
              </div>
              {renameImpactByEvidenceIndex.get(index) ? (
                <div className="notice">
                  <strong>改名会影响已有技能关联</strong>
                  <p>
                    “{renameImpactByEvidenceIndex.get(index)?.previousKey}”当前被技能
                    {renameImpactByEvidenceIndex.get(index)?.affectedSkillNames.join("、")} 引用。
                    直接保存新简称会让这些既有引用失效；这里只迁移已有引用，不会新增技能或能力判断。
                  </p>
                  <button
                    className="button-secondary"
                    type="button"
                    onClick={() => migrateRenamedEvidenceReferences(index)}
                  >
                    将这些已有技能引用迁移到“{renameImpactByEvidenceIndex.get(index)?.nextKey}”
                  </button>
                </div>
              ) : null}
              {contentImpactByEvidenceIndex.get(index) ? (
                <div className="notice">
                  <strong>清空内容会让已有技能失去证据</strong>
                  <p>
                    这段经历仍被技能
                    {contentImpactByEvidenceIndex.get(index)?.affectedSkillNames.join("、")} 引用，但“我做了什么”已经为空。
                    你可以补回真实经历内容，或显式移除这些既有引用；JobLens 不会自动替你补事实。
                  </p>
                  <button
                    className="button-secondary"
                    type="button"
                    onClick={() => detachEmptyEvidenceReferences(index)}
                  >
                    只移除这些技能引用
                  </button>
                </div>
              ) : null}
              {deleteImpactByEvidenceIndex.get(index) ? (
                <div className="notice">
                  <strong>删除会影响已有技能关联</strong>
                  <p>
                    这段经历当前被技能
                    {deleteImpactByEvidenceIndex.get(index)?.affectedSkillNames.join("、")} 引用。
                    删除时必须同时移除这些既有引用；JobLens 不会把失效 Evidence key 留在技能中，也不会替你补造新的证据。
                  </p>
                  <button
                    className="danger-link"
                    type="button"
                    disabled={evidence.length === 1}
                    onClick={() => deleteEvidenceAndRemoveReferences(index)}
                  >
                    同时移除这些技能引用并删除这段经历
                  </button>
                </div>
              ) : (
                <button
                  className="danger-link"
                  type="button"
                  disabled={evidence.length === 1}
                  onClick={() => deleteEvidenceAndRemoveReferences(index)}
                >
                  删除这段经历
                </button>
              )}
            </article>
          ))}
        </div>

        <div className="subsection-heading">
          <div>
            <h3>我的技能</h3>
            <p>每项技能至少选择一段能证明它的真实经历，避免把“想学”误当成“已经会”。</p>
          </div>
          <button
            className="button-secondary"
            type="button"
            onClick={() => {
              markProfileDirty();
              setSkills((items) => [...items, {...EMPTY_SKILL}]);
            }}
          >
            + 添加技能
          </button>
        </div>

        <div className="editor-list">
          {skills.map((item, index) => (
            <article className="editor-card" id={`profile-skill-${index}`} key={`skill-${index}`}>
              <div className="editor-card-grid">
                <div className="field">
                  <label htmlFor={`skill-name-${index}`}>技能名称</label>
                  <input
                    id={`skill-name-${index}`}
                    value={item.name}
                    onChange={(event) => updateSkill(index, {name: event.target.value})}
                    placeholder="例如：React、TypeScript、Agent 应用开发"
                    required
                  />
                </div>
                <div className="field">
                  <label htmlFor={`skill-level-${index}`}>熟练度</label>
                  <select
                    id={`skill-level-${index}`}
                    value={item.level}
                    onChange={(event) =>
                      updateSkill(index, {level: event.target.value as SkillLevel})
                    }
                  >
                    <option value="strong">强项</option>
                    <option value="working">可工作使用</option>
                    <option value="basic">基础了解</option>
                    <option value="unknown">待确认</option>
                  </select>
                </div>
              </div>
              <fieldset className="evidence-picker">
                <legend>哪些经历能证明这项技能</legend>
                {selectableEvidence.length === 0 ? (
                  <p>先补充上面的经历与成果。</p>
                ) : (
                  selectableEvidence.map((key) => (
                    <label key={key}>
                      <input
                        type="checkbox"
                        checked={item.evidenceKeys.includes(key)}
                        onChange={() => toggleSkillEvidence(index, key)}
                      />
                      {key}
                    </label>
                  ))
                )}
              </fieldset>
              <button
                className="danger-link"
                type="button"
                disabled={skills.length === 1}
                onClick={() => {
                  markProfileDirty();
                  setSkills((items) => items.filter((_, i) => i !== index));
                }}
              >
                删除技能
              </button>
            </article>
          ))}
        </div>

            <div className="actions">
              <button
                className="button-secondary"
                type="button"
                onClick={() => {
                  setIsProfileEditorOpen(false);
                  focusProfileDraft();
                }}
              >
                完成编辑，返回审核
              </button>
            </div>
          </section>
        ) : null}

        {profileState.kind !== "idle" ? (
          <p className={profileState.kind === "error" ? "inline-error" : "notice"}>
            {profileState.message}
          </p>
        ) : null}
      </form>

      <form className="panel profile-form" onSubmit={saveIntent}>
        <div className="section-title-row">
          <div>
            <p className="eyebrow">我想找什么</p>
            <h2>求职偏好</h2>
          </div>
          <span className="version-badge">{intentVersion > 0 ? "已保存" : "尚未保存"}</span>
        </div>

        <div className="profile-grid">
          <div className="field profile-span-2">
            <label htmlFor="targetRoles">目标岗位（每行或逗号分隔）</label>
            <textarea
              id="targetRoles"
              value={targetRoles}
              onChange={(event) => setTargetRoles(event.target.value)}
              placeholder={"AI 应用工程师\nAgent 工程师"}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="cities">目标城市</label>
            <textarea
              id="cities"
              value={cities}
              onChange={(event) => setCities(event.target.value)}
              placeholder={"武汉\n长沙"}
            />
          </div>
          <div className="field">
            <label htmlFor="minimumSalaryK">最低薪资 K/月</label>
            <input
              id="minimumSalaryK"
              type="number"
              min="0"
              value={minimumSalaryK}
              onChange={(event) => setMinimumSalaryK(event.target.value)}
              placeholder="20"
            />
          </div>
          <div className="field">
            <label htmlFor="remoteAccepted">接受远程</label>
            <select
              id="remoteAccepted"
              value={remoteAccepted}
              onChange={(event) => setRemoteAccepted(event.target.value)}
            >
              <option value="">未设置</option>
              <option value="true">接受</option>
              <option value="false">不接受</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="seniority">目标级别</label>
            <select
              id="seniority"
              value={seniority}
              onChange={(event) => setSeniority(event.target.value as Seniority | "")}
            >
              <option value="">未设置</option>
              <option value="intern">实习</option>
              <option value="junior">初级</option>
              <option value="mid">中级</option>
              <option value="senior">高级</option>
              <option value="staff">资深专家（Staff）</option>
              <option value="lead">技术负责人（Lead）</option>
              <option value="principal">首席 / 专家（Principal）</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="employmentTypes">工作形式</label>
            <textarea
              id="employmentTypes"
              value={employmentTypes}
              onChange={(event) => setEmploymentTypes(event.target.value)}
              placeholder="例如：全职、合同、兼职"
            />
          </div>
          <div className="field">
            <label htmlFor="excludeKeywords">排除关键词</label>
            <textarea
              id="excludeKeywords"
              value={excludeKeywords}
              onChange={(event) => setExcludeKeywords(event.target.value)}
              placeholder="博彩"
            />
          </div>
          <div className="field profile-span-2">
            <label htmlFor="hardConstraints">不能接受的条件</label>
            <textarea
              id="hardConstraints"
              value={hardConstraints}
              onChange={(event) => setHardConstraints(event.target.value)}
              placeholder="不接受长期驻场"
            />
          </div>
          <div className="field profile-span-2">
            <label htmlFor="softPreferences">更喜欢的条件</label>
            <textarea
              id="softPreferences"
              value={softPreferences}
              onChange={(event) => setSoftPreferences(event.target.value)}
              placeholder="AI 产品有真实用户"
            />
          </div>
        </div>

        <div className="actions">
          <button className="button" type="submit" disabled={intentState.kind === "saving"}>
            保存求职偏好
          </button>
        </div>
        {intentState.kind !== "idle" ? (
          <p className={intentState.kind === "error" ? "inline-error" : "notice"}>
            {intentState.message}
          </p>
        ) : null}
      </form>
    </div>
  );
}
