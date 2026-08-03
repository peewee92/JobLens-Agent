"use client";

import {useRouter} from "next/navigation";
import {FormEvent, useMemo, useState} from "react";

import {ResumeProposalPanel} from "@/components/resume-proposal-panel";
import {proposalToProfileDraft} from "@/lib/profile-proposal";
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
    return body.error?.message ?? `保存失败（${response.status}）。`;
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
    setProfileState({kind: "saving", message: "正在保存职业画像…"});
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
        message: `职业画像已确认并保存为版本 ${saved.version}。`,
      });
      router.refresh();
    } catch {
      setProfileState({kind: "error", message: "保存失败，请确认 Web 与 Backend 已启动。"});
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
    setIntentState({kind: "saving", message: "正在保存求职意向…"});
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
        message: `求职意向已保存为版本 ${saved.version}。`,
      });
      router.refresh();
    } catch {
      setIntentState({kind: "error", message: "保存失败，请确认 Web 与 Backend 已启动。"});
    }
  }

  return (
    <div className="profile-layout">
      <ResumeProposalPanel onApply={applyProposal} />
      <form className="panel profile-form" onSubmit={saveProfile}>
        <div className="section-title-row">
          <div>
            <p className="eyebrow">Confirmed facts</p>
            <h2>职业画像</h2>
          </div>
          <span className="version-badge">当前版本 {profileVersion}</span>
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
            <h3>Evidence</h3>
            <p>先记录真实经历，再让技能引用这些证据。</p>
          </div>
          <button
            className="button-secondary"
            type="button"
            onClick={() => setEvidence((items) => [...items, {...EMPTY_EVIDENCE}])}
          >
            + 添加证据
          </button>
        </div>

        <div className="editor-list">
          {evidence.map((item, index) => (
            <article className="editor-card" key={`evidence-${index}`}>
              <div className="editor-card-grid">
                <div className="field">
                  <label htmlFor={`evidence-key-${index}`}>引用 key</label>
                  <input
                    id={`evidence-key-${index}`}
                    value={item.key}
                    onChange={(event) => updateEvidence(index, {key: event.target.value})}
                    placeholder="joblens-project"
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
                  <label htmlFor={`evidence-summary-${index}`}>事实摘要</label>
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
                <div className="field profile-span-2">
                  <label htmlFor={`evidence-source-${index}`}>来源</label>
                  <input
                    id={`evidence-source-${index}`}
                    value={item.source}
                    onChange={(event) =>
                      updateEvidence(index, {source: event.target.value})
                    }
                    placeholder="confirmed by user"
                    required
                  />
                </div>
              </div>
              <button
                className="danger-link"
                type="button"
                disabled={evidence.length === 1}
                onClick={() => setEvidence((items) => items.filter((_, i) => i !== index))}
              >
                删除证据
              </button>
            </article>
          ))}
        </div>

        <div className="subsection-heading">
          <div>
            <h3>技能与证据链接</h3>
            <p>每个技能至少勾选一条 Evidence，否则 Backend 会拒绝新版本。</p>
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
                    placeholder="Agent Application Engineering"
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
                <legend>支撑 Evidence</legend>
                {selectableEvidence.length === 0 ? (
                  <p>先填写 Evidence key。</p>
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
            保存职业画像新版本
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
            <p className="eyebrow">Search constraints</p>
            <h2>求职意向</h2>
          </div>
          <span className="version-badge">当前版本 {intentVersion}</span>
        </div>

        <div className="profile-grid">
          <div className="field profile-span-2">
            <label htmlFor="targetRoles">目标岗位（每行或逗号分隔）</label>
            <textarea
              id="targetRoles"
              value={targetRoles}
              onChange={(event) => setTargetRoles(event.target.value)}
              placeholder={"AI Application Engineer\nAgent Engineer"}
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
              <option value="staff">Staff</option>
              <option value="lead">Lead</option>
              <option value="principal">Principal</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="employmentTypes">雇佣类型</label>
            <textarea
              id="employmentTypes"
              value={employmentTypes}
              onChange={(event) => setEmploymentTypes(event.target.value)}
              placeholder="full_time"
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
            <label htmlFor="hardConstraints">硬约束（未来 Eligibility 使用）</label>
            <textarea
              id="hardConstraints"
              value={hardConstraints}
              onChange={(event) => setHardConstraints(event.target.value)}
              placeholder="不接受长期驻场"
            />
          </div>
          <div className="field profile-span-2">
            <label htmlFor="softPreferences">软偏好（未来 Ranking 使用）</label>
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
            保存求职意向新版本
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
