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
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [proposal, setProposal] = useState<ProfileExtractionProposal | null>(null);
  const [state, setState] = useState<ProposalState>({kind: "idle", message: ""});

  async function acceptResponse(response: Response) {
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
  }

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
      await acceptResponse(response);
    } catch {
      setState({kind: "error", message: "请求失败，请确认 Web 与 Backend 已启动。"});
    }
  }

  async function proposeFile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!resumeFile) return;
    setProposal(null);
    setState({kind: "submitting", message: "正在解析文件并生成待确认提案…"});
    const form = new FormData();
    form.set("file", resumeFile, resumeFile.name);
    try {
      const response = await fetch("/api/profile-proposals/file", {
        method: "POST",
        body: form,
      });
      await acceptResponse(response);
    } catch {
      setState({kind: "error", message: "请求失败，请确认 Web 与 Backend 已启动。"});
    }
  }

  return (
    <section className="panel proposal-panel" aria-labelledby="resume-proposal-title">
      <div className="section-heading-row">
        <div>
          <p className="eyebrow">Profile Extraction Proposal</p>
          <h2 id="resume-proposal-title">从简历生成待确认提案</h2>
        </div>
        <span className="version-badge">不会自动保存</span>
      </div>
      <p className="muted-copy">
        可上传 5 MiB 内的文本型 PDF/DOCX，或直接粘贴文本。扫描 PDF 暂不支持 OCR。模型输出只是草稿；只有你采用并再次保存职业画像，事实才会进入 confirmed Profile。
      </p>

      <form className="proposal-file-form" onSubmit={proposeFile}>
        <div className="file-field compact-file-field">
          <span>上传 PDF 或 DOCX</span>
          <input
            type="file"
            accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            onChange={(event) => setResumeFile(event.target.files?.[0] ?? null)}
          />
        </div>
        <div className="actions">
          <button
            className="button-secondary"
            type="submit"
            disabled={state.kind === "submitting" || !resumeFile}
          >
            {state.kind === "submitting" ? "处理中…" : "从文件生成提案"}
          </button>
          <span className="muted-copy">
            {resumeFile ? `${resumeFile.name} · ${Math.ceil(resumeFile.size / 1024)} KiB` : "未选择文件"}
          </span>
        </div>
      </form>

      <div className="proposal-divider"><span>或粘贴纯文本</span></div>

      <form onSubmit={propose}>
        <div className="field">
          <label htmlFor="resumeText">简历纯文本</label>
          <textarea
            id="resumeText"
            value={resumeText}
            onChange={(event) => setResumeText(event.target.value)}
            rows={10}
            maxLength={30000}
            placeholder="粘贴简历或项目经历文本。"
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
