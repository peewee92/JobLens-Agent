"use client";

import {useRouter} from "next/navigation";
import {FormEvent, useMemo, useRef, useState} from "react";

import {ResumeProposalPanel} from "@/components/resume-proposal-panel";
import {
  isBlankProfileDraft,
  proposalToProfileDraft,
} from "@/lib/profile-proposal";
import {userFacingApiError} from "@/lib/user-facing-errors";
import type {
  ApiErrorBody,
  EvidenceType,
  ProfileExtractionProposal,
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
}: {
  initialProfile: UserProfile | null;
  initialIntent: SearchIntent | null;
  afterProfileSaveHref?: string | null;
  focusEvidenceType?: EvidenceType | null;
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
  const [skills, setSkills] = useState<SkillDraft[]>(initialSkills(initialProfile));
  const [profileState, setProfileState] = useState<SaveState>({
    kind: "idle",
    message: "",
  });
  const [profileDirty, setProfileDirty] = useState(false);
  const [isProfileEditorOpen, setIsProfileEditorOpen] = useState(Boolean(focusEvidenceType));

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

  function addFocusedEvidence() {
    if (!focusEvidenceType) return;
    markProfileDirty();
    setEvidence((items) => {
      const blankIndex = items.findIndex(
        (item) => !item.key.trim() && !item.summary.trim(),
      );
      if (blankIndex >= 0) {
        return items.map((item, index) =>
          index === blankIndex ? {...item, type: focusEvidenceType} : item,
        );
      }
      return [...items, {...EMPTY_EVIDENCE, type: focusEvidenceType}];
    });
    setIsProfileEditorOpen(true);
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

        {focusEvidenceType === "education" ? (
          <section className="notice" id="profile-evidence-focus">
            <strong>先补教育事实，再回到岗位优先级重算</strong>
            <p>
              当前已有匹配结果里存在学历或专业硬条件，但你的已确认 Profile 还缺少足够直接的教育证据。只填写真实信息；学历层级、专业和岗位明确要求的院校限定会直接影响 Eligibility 判断。
            </p>
            <p className="muted">
              {focusedEvidenceCount > 0
                ? `当前草稿里已有 ${focusedEvidenceCount} 条教育经历，请检查关键信息是否写完整。`
                : "当前草稿还没有完整的教育经历条目。"}
            </p>
            <div className="actions">
              <button className="button-secondary" type="button" onClick={addFocusedEvidence}>
                + 添加教育经历
              </button>
            </div>
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
            }}
          >
            + 添加经历
          </button>
        </div>

        <div className="editor-list">
          {evidence.map((item, index) => (
            <article className="editor-card" key={`evidence-${index}`}>
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
              <button
                className="danger-link"
                type="button"
                disabled={evidence.length === 1}
                onClick={() => {
                  markProfileDirty();
                  setEvidence((items) => items.filter((_, i) => i !== index));
                }}
              >
                删除这段经历
              </button>
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
            <article className="editor-card" key={`skill-${index}`}>
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
