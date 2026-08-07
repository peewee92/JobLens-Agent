"use client";

import {useRouter} from "next/navigation";
import {FormEvent, useMemo, useState} from "react";

import {ResumeProposalPanel} from "@/components/resume-proposal-panel";
import {proposalToProfileDraft} from "@/lib/profile-proposal";
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
}: {
  initialProfile: UserProfile | null;
  initialIntent: SearchIntent | null;
}) {
  const router = useRouter();
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

  function updateEvidence(index: number, patch: Partial<EvidenceDraft>) {
    setEvidence((items) =>
      items.map((item, itemIndex) =>
        itemIndex === index ? {...item, ...patch} : item,
      ),
    );
  }

  function updateSkill(index: number, patch: Partial<SkillDraft>) {
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
      setProfileState({
        kind: "success",
        message: "职业背景已保存。后续匹配会使用这份你确认过的信息。",
      });
      router.refresh();
    } catch {
      setProfileState({kind: "error", message: "保存失败，请稍后重试。"});
    }
  }

  function applyProposal(proposal: ProfileExtractionProposal) {
    const draft = proposalToProfileDraft(proposal);
    setHeadline(draft.headline);
    setYears(draft.years);
    setEvidence(draft.evidence);
    setSkills(draft.skills);
    setProfileState({
      kind: "idle",
      message: `已采用提案 ${proposal.runId} 到编辑表单；请继续核对并手动保存。`,
    });
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
      <ResumeProposalPanel onApply={applyProposal} />
      <form className="panel profile-form" onSubmit={saveProfile}>
        <div className="section-title-row">
          <div>
            <p className="eyebrow">我的真实经历</p>
            <h2>我的职业背景</h2>
          </div>
          <span className="version-badge">{profileVersion > 0 ? "已保存" : "尚未保存"}</span>
        </div>

        <div className="profile-grid">
          <div className="field profile-span-2">
            <label htmlFor="headline">职业定位</label>
            <input
              id="headline"
              value={headline}
              onChange={(event) => setHeadline(event.target.value)}
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
              onChange={(event) => setYears(event.target.value)}
              placeholder="8"
            />
          </div>
        </div>

        <div className="subsection-heading">
          <div>
            <h3>经历与成果</h3>
            <p>记录真正做过的工作、项目、教育和成果，后面的技能需要从这些经历中找到依据。</p>
          </div>
          <button
            className="button-secondary"
            type="button"
            onClick={() => setEvidence((items) => [...items, {...EMPTY_EVIDENCE}])}
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
                onClick={() => setEvidence((items) => items.filter((_, i) => i !== index))}
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
            onClick={() => setSkills((items) => [...items, {...EMPTY_SKILL}])}
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
                onClick={() => setSkills((items) => items.filter((_, i) => i !== index))}
              >
                删除技能
              </button>
            </article>
          ))}
        </div>

        <div className="actions">
          <button className="button" type="submit" disabled={profileState.kind === "saving"}>
            保存我的职业背景
          </button>
        </div>
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
