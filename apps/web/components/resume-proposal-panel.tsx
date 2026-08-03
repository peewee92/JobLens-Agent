"use client";

import {FormEvent, useState} from "react";

import type {
  ApiErrorBody,
  ProfileExtractionProposal,
} from "@/lib/contracts";

type ProposalState = {
  kind: "idle" | "submitting" | "success" | "error";
  message: string;
};

async function apiMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as Partial<ApiErrorBody>;
    return body.error?.message ?? `提案生成失败（${response.status}）。`;
  } catch {
    return `提案生成失败（${response.status}）。`;
  }
}

export function ResumeProposalPanel({
  onApply,
}: {
  onApply: (proposal: ProfileExtractionProposal) => void;
}) {
  const [resumeText, setResumeText] = useState("");
  const [proposal, setProposal] = useState<ProfileExtractionProposal | null>(null);
  const [state, setState] = useState<ProposalState>({kind: "idle", message: ""});

  async function propose(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setProposal(null);
    setState({kind: "submitting", message: "正在生成待确认提案…"});
    try {
      const response = await fetch("/api/profile-proposals", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({resumeText}),
      });
      if (!response.ok) {
        setState({kind: "error", message: await apiMessage(response)});
        return;
      }
      const result = (await response.json()) as ProfileExtractionProposal;
      setProposal(result);
      setState({
        kind: "success",
        message: "提案已生成。请逐项检查证据片段，再决定是否采用。",
      });
    } catch {
      setState({kind: "error", message: "请求失败，请确认 Web 与 Backend 已启动。"});
    }
  }

  return (
    <section className="panel proposal-panel" aria-labelledby="resume-proposal-title">
      <div className="section-heading-row">
        <div>
          <p className="eyebrow">Profile Extraction Proposal</p>
          <h2 id="resume-proposal-title">从简历文本生成待确认提案</h2>
        </div>
        <span className="version-badge">不会自动保存</span>
      </div>
      <p className="muted-copy">
        模型输出只是草稿。每条 Evidence 必须携带简历原文片段，并经过后端确定性校验；只有你点击采用并再次保存职业画像，事实才会进入 confirmed Profile。
      </p>

      <form onSubmit={propose}>
        <div className="field">
          <label htmlFor="resumeText">简历纯文本</label>
          <textarea
            id="resumeText"
            value={resumeText}
            onChange={(event) => setResumeText(event.target.value)}
            rows={10}
            maxLength={30000}
            placeholder="粘贴简历或项目经历文本。当前切片不解析 PDF/DOCX。"
          />
        </div>
        <div className="actions proposal-actions">
          <button
            className="button"
            type="submit"
            disabled={state.kind === "submitting" || resumeText.trim().length < 50}
          >
            {state.kind === "submitting" ? "生成中…" : "生成待确认提案"}
          </button>
          <span className="muted-copy">{resumeText.trim().length} / 30000 字符</span>
        </div>
      </form>

      {state.message ? (
        <div className={state.kind === "error" ? "inline-error" : "notice"}>
          {state.message}
        </div>
      ) : null}

      {proposal ? (
        <div className="proposal-result">
          <div className="meta-row">
            <span className="tag code">{proposal.runId}</span>
            <span className="tag">模型：{proposal.model}</span>
            <span className="tag">Prompt：{proposal.promptVersion}</span>
          </div>
          <h3>{proposal.headline}</h3>
          <p className="muted-copy">
            经验年限：{proposal.yearsOfExperience ?? "未从原文确认"}
          </p>

          <div className="proposal-grid">
            <section>
              <h3>Evidence 提案</h3>
              {proposal.evidence.map((item) => (
                <article className="proposal-item" key={item.key}>
                  <strong>{item.key}</strong>
                  <span className="tag">{item.type}</span>
                  <p>{item.summary}</p>
                  <blockquote>{item.evidenceSpan}</blockquote>
                </article>
              ))}
            </section>
            <section>
              <h3>Skill 提案</h3>
              {proposal.skills.map((item) => (
                <article className="proposal-item" key={item.name}>
                  <strong>{item.name}</strong>
                  <span className="tag">{item.level}</span>
                  <p>Evidence：{item.evidenceKeys.join("、")}</p>
                </article>
              ))}
            </section>
          </div>

          {proposal.warnings.length ? (
            <div className="notice">
              <strong>提案提醒</strong>
              <ul>
                {proposal.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <button
            className="button-secondary"
            type="button"
            onClick={() => onApply(proposal)}
          >
            采用到下方编辑表单
          </button>
        </div>
      ) : null}
    </section>
  );
}
