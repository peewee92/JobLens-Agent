"use client";

import {DragEvent, FormEvent, useState} from "react";

import type {
  ApiErrorBody,
  EvidenceType,
  ProfileExtractionProposal,
  SkillLevel,
} from "@/lib/contracts";
import {validateResumeFile} from "@/lib/resume-files";
import {userFacingApiError} from "@/lib/user-facing-errors";

type ProposalState = {
  kind: "idle" | "submitting" | "success" | "error";
  message: string;
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

async function apiMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as Partial<ApiErrorBody>;
    return userFacingApiError(body, `简历整理失败（${response.status}），请稍后重试。`);
  } catch {
    return `简历整理失败（${response.status}）。`;
  }
}

export function ResumeProposalPanel({
  onApply,
}: {
  onApply: (proposal: ProfileExtractionProposal) => void;
}) {
  const [resumeText, setResumeText] = useState("");
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [isDraggingFile, setIsDraggingFile] = useState(false);
  const [proposal, setProposal] = useState<ProfileExtractionProposal | null>(null);
  const [state, setState] = useState<ProposalState>({kind: "idle", message: ""});

  function selectResumeFile(file: File | null) {
    setProposal(null);
    if (!file) {
      setResumeFile(null);
      setState({kind: "idle", message: ""});
      return;
    }
    const validationError = validateResumeFile(file);
    if (validationError) {
      setResumeFile(null);
      setState({kind: "error", message: validationError});
      return;
    }
    setResumeFile(file);
    setState({kind: "idle", message: ""});
  }

  function dropResumeFile(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDraggingFile(false);
    const files = event.dataTransfer.files;
    if (files.length !== 1) {
      setProposal(null);
      setResumeFile(null);
      setState({kind: "error", message: "一次请只拖入 1 个 PDF 或 DOCX 文件。"});
      return;
    }
    selectResumeFile(files[0] ?? null);
  }

  async function acceptResponse(response: Response) {
    if (!response.ok) {
      setState({kind: "error", message: await apiMessage(response)});
      return;
    }
    const result = (await response.json()) as ProfileExtractionProposal;
    setProposal(result);
    setState({
      kind: "success",
      message: "简历草稿已生成。请逐项检查，确认没有遗漏或写错，再填入你的职业背景。",
    });
  }

  async function propose(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setProposal(null);
    setState({kind: "submitting", message: "正在整理你的简历…"});
    try {
      const response = await fetch("/api/profile-proposals", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({resumeText}),
      });
      await acceptResponse(response);
    } catch {
      setState({kind: "error", message: "暂时无法整理简历，请稍后重试。"});
    }
  }

  async function proposeFile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!resumeFile) return;
    setProposal(null);
    setState({kind: "submitting", message: "正在读取文件并整理你的简历…"});
    const form = new FormData();
    form.set("file", resumeFile, resumeFile.name);
    try {
      const response = await fetch("/api/profile-proposals/file", {
        method: "POST",
        body: form,
      });
      await acceptResponse(response);
    } catch {
      setState({kind: "error", message: "暂时无法整理简历，请稍后重试。"});
    }
  }

  return (
    <section className="panel proposal-panel" aria-labelledby="resume-proposal-title">
      <div className="section-heading-row">
        <div>
          <p className="eyebrow">AI 简历整理</p>
          <h2 id="resume-proposal-title">从简历快速填充职业背景</h2>
        </div>
        <span className="version-badge">不会自动保存</span>
      </div>
      <p className="muted-copy">
        可上传 5 MiB 内的 PDF/DOCX，或直接粘贴文本。扫描版 PDF 暂时无法识别。AI 只会生成待确认草稿，必须由你检查并保存后，才会用于岗位匹配。
      </p>

      <form className="proposal-file-form" onSubmit={proposeFile}>
        <div
          className={`file-field compact-file-field drop-file-field${isDraggingFile ? " is-dragging" : ""}`}
          onDragEnter={(event) => {
            event.preventDefault();
            setIsDraggingFile(true);
          }}
          onDragOver={(event) => {
            event.preventDefault();
            event.dataTransfer.dropEffect = "copy";
            setIsDraggingFile(true);
          }}
          onDragLeave={() => setIsDraggingFile(false)}
          onDrop={dropResumeFile}
        >
          <span>上传 PDF 或 DOCX</span>
          <p className="muted-copy file-drop-hint">
            {isDraggingFile ? "松开即可添加文件" : "拖拽文件到这里，或点击下方选择文件"}
          </p>
          <input
            type="file"
            accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            onChange={(event) => selectResumeFile(event.target.files?.[0] ?? null)}
          />
        </div>
        <div className="actions">
          <button
            className="button-secondary"
            type="submit"
            disabled={state.kind === "submitting" || !resumeFile}
          >
            {state.kind === "submitting" ? "处理中…" : "整理这份简历"}
          </button>
          <span className="muted-copy" aria-live="polite">
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
            {state.kind === "submitting" ? "整理中…" : "整理这段简历文本"}
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
          <details className="technical-details">
            <summary>查看技术详情</summary>
            <p className="code">run={proposal.runId} · model={proposal.model} · prompt={proposal.promptVersion}</p>
          </details>
          <h3>{proposal.headline}</h3>
          <p className="muted-copy">
            经验年限：{proposal.yearsOfExperience ?? "未从原文确认"}
          </p>

          <div className="proposal-grid">
            <section>
              <h3>经历草稿</h3>
              {proposal.evidence.map((item) => (
                <article className="proposal-item" key={item.key}>
                  <strong>{item.summary}</strong>
                  <span className="tag">{evidenceTypeLabels[item.type]}</span>
                  <p className="muted-copy">经历简称：{item.key}</p>
                  <blockquote>{item.evidenceSpan}</blockquote>
                </article>
              ))}
            </section>
            <section>
              <h3>技能草稿</h3>
              {proposal.skills.map((item) => (
                <article className="proposal-item" key={item.name}>
                  <strong>{item.name}</strong>
                  <span className="tag">{skillLevelLabels[item.level]}</span>
                  <p>
                    依据经历：{item.evidenceKeys.map((key) => proposal.evidence.find((evidence) => evidence.key === key)?.summary ?? key).join("、")}
                  </p>
                </article>
              ))}
            </section>
          </div>

          {proposal.warnings.length ? (
            <div className="notice">
              <strong>请重点检查</strong>
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
            填到下方，继续检查和修改
          </button>
        </div>
      ) : null}
    </section>
  );
}
