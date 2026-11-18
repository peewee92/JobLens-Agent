"use client";

import {DragEvent, FormEvent, useRef, useState} from "react";

import type {
  ApiErrorBody,
  EvidenceType,
  ProfileExtractionProposal,
  SkillLevel,
} from "@/lib/contracts";
import {Button} from "@/components/ui/button";
import {ActionFeedback} from "@/components/ui/patterns";
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
  byok = false,
  localProfileModel = null,
  onProposalReady,
  onApply,
  onReviewDraft,
  onManualEntry,
  manualEntryLabel = "不用简历，快速填写",
  hideManualEntry = false,
  disabled = false,
}: {
  byok?: boolean;
  localProfileModel?: boolean | null;
  onProposalReady: (proposal: ProfileExtractionProposal) => boolean;
  onApply: (proposal: ProfileExtractionProposal) => void;
  onReviewDraft: () => void;
  onManualEntry?: () => void;
  manualEntryLabel?: string;
  hideManualEntry?: boolean;
  disabled?: boolean;
}) {
  const authorizeModel = byok || localProfileModel === true;
  const unavailable = localProfileModel === false;
  const [callPlan, setCallPlan] = useState<{
    planDigest: string; model: string; destination?: string; maxProviderCalls: number; maxOutputTokens: number;
  } | null>(null);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const inFlight = useRef(false);
  const [source, setSource] = useState<"file" | "text">(byok ? "text" : "file");
  const [resumeText, setResumeText] = useState("");
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [isDraggingFile, setIsDraggingFile] = useState(false);
  const [proposal, setProposal] = useState<ProfileExtractionProposal | null>(null);
  const [proposalApplied, setProposalApplied] = useState(false);
  const [state, setState] = useState<ProposalState>({kind: "idle", message: ""});

  function selectResumeFile(file: File | null) {
    if (inFlight.current || disabled) return;
    setSource("file");
    setCallPlan(null); setPendingAction(null);
    setProposal(null);
    setProposalApplied(false);
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
    if (inFlight.current || disabled) return;
    setSource("file");
    const files = event.dataTransfer.files;
    if (files.length !== 1) {
      setCallPlan(null); setPendingAction(null);
      setProposal(null);
      setProposalApplied(false);
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
    const autoApplied = onProposalReady(result);
    setProposal(result);
    setProposalApplied(autoApplied);
    setState({
      kind: "success",
      message: `已整理 ${result.evidence.length} 条经历、${result.skills.length} 项技能。${autoApplied
        ? "已填入待核对的草稿，尚未保存。"
        : "尚未替换当前资料，请先查看草稿再决定。"}`,
    });
  }

  async function propose(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current || disabled || unavailable || resumeText.trim().length < 50) return;
    inFlight.current = true;
    setSource("text");
    setCallPlan(null); setPendingAction(null);
    setProposal(null);
    setProposalApplied(false);
    setState({kind: "submitting", message: "正在整理你的简历…"});
    try {
      if (authorizeModel) {
        const r = await fetch(byok ? "/api/byok/profile-call-plan" : "/api/local/profile-model/plan", {method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({resumeText})});
        if (!r.ok) { setState({kind: "error", message: await apiMessage(r)}); return; }
        setCallPlan(await r.json()); setPendingAction(null);
        setState({kind: "idle", message: "请核对下方调用计划；尚未发送模型请求。"}); return;
      }
      const response = await fetch("/api/profile-proposals", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({resumeText}),
      });
      await acceptResponse(response);
    } catch {
      setState({kind: "error", message: "暂时无法整理简历，可重试或手动填写。职业资料没有自动保存。"});
    } finally {
      inFlight.current = false;
    }
  }

  async function executePlan() {
    if (!callPlan || disabled || inFlight.current) return;
    inFlight.current = true;
    const id = pendingAction ?? crypto.randomUUID(); setPendingAction(id);
    setState({kind:"submitting", message:"正在使用你的模型整理背景……"});
    try {
      const response = await fetch(byok ? "/api/byok/profile-calls" : "/api/local/profile-model/calls", {method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({actionId:id, planDigest:callPlan.planDigest, confirmed:true, maxProviderCalls:1})});
      const record = await response.json();
      if (response.ok && record.status === "failed") {
        setState({kind: "error", message: record.errorCode === "provider_payment_required"
          ? "模型服务余额或计费不可用，没有得到草稿。可手填经历，或解决计费后重新授权。"
          : record.errorCode === "provider_auth_failed" || record.errorCode === "provider_forbidden"
            ? "模型服务拒绝了授权，请检查配置，或手填经历。"
            : "没能从这次模型结果整理出可核对的草稿。没有保存或改动职业背景；可以先快速填写一段经历。"});
        setCallPlan(null);
        return;
      }
      if (!response.ok || record.status !== "completed" || !record.result) throw new Error();
      await acceptResponse(new Response(JSON.stringify(record.result), {status:200}));
      setCallPlan(null);
    } catch {setState({kind:"error", message:"未取得可用草稿。结果可能未知；再次点击只查询／重放同一请求，不会自动重新付费。也可以先手动填写。"});}
    finally { inFlight.current = false; }
  }

  async function proposeFile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!resumeFile || disabled || unavailable || inFlight.current) return;
    inFlight.current = true;
    setSource("file");
    setCallPlan(null); setPendingAction(null);
    setProposal(null);
    setProposalApplied(false);
    setState({kind: "submitting", message: "正在读取文件并整理你的简历…"});
    const form = new FormData();
    form.set("file", resumeFile, resumeFile.name);
    try {
      const response = await fetch(authorizeModel ? "/api/local/profile-model/file-plan" : "/api/profile-proposals/file", {
        method: "POST",
        body: form,
      });
      if (authorizeModel && response.ok) {
        setCallPlan(await response.json());
        setState({kind: "idle", message: "已在本机读取文件；尚未发送给模型。"});
        return;
      }
      await acceptResponse(response);
    } catch {
      setState({kind: "error", message: "暂时无法整理简历，可重试或手动填写。职业资料没有自动保存。"});
    } finally {
      inFlight.current = false;
    }
  }

  const busy = state.kind === "submitting";
  const feedback = state.message && <ActionFeedback tone={state.kind === "error" ? "danger" : "info"}>{state.message}</ActionFeedback>;

  return (
    <section className="panel proposal-panel" aria-labelledby="resume-proposal-title">
      <div className="section-heading-row">
        <div>
          <p className="eyebrow">第 1 步 · {byok ? "添加简历文字" : "上传简历"}</p>
          <h2 id="resume-proposal-title">{unavailable ? "先填写你的真实经历" : byok ? "粘贴简历，先生成草稿" : "上传简历，先生成草稿"}</h2>
        </div>
        <span className="version-badge">自动填草稿 · 不自动保存</span>
      </div>
      <p className="muted-copy">
        {byok
          ? "你可以粘贴简历文字。确认调用后，内容才会发送给你选择的模型服务。"
          : authorizeModel
            ? "支持 5 MiB 内、可选中文字的 PDF 或 DOCX。文件在本机读取；只有确认调用后，提取出的文本才会发送给模型服务。"
            : unavailable
              ? "还没配置可用的简历模型。可先手动填写真实经历，之后再从本地启动配置接入模型。"
              : "支持 5 MiB 内、可选中文字的 PDF 或 DOCX。离线演示只使用样本规则；其他模式需先配置并授权模型。"} 整理只生成草稿，只有你核对保存后才会用于匹配。
      </p>

      {!byok && !unavailable && <form className="proposal-file-form" method="post" onSubmit={proposeFile}>
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
            aria-label="选择简历 PDF 或 DOCX"
            disabled={busy || disabled}
            accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            onChange={(event) => selectResumeFile(event.target.files?.[0] ?? null)}
          />
        </div>
        <div className="actions">
          <button
            className="button-secondary"
            type="submit"
            disabled={busy || disabled || !resumeFile}
          >
            {state.kind === "submitting" ? "处理中…" : authorizeModel ? "读取文件，查看模型调用计划" : "整理这份简历"}
          </button>
          <span className="muted-copy" aria-live="polite">
            {resumeFile ? `${resumeFile.name} · ${Math.ceil(resumeFile.size / 1024)} KiB` : "未选择文件"}
          </span>
        </div>
        {source === "file" && !(callPlan && pendingAction) ? feedback : null}
      </form>}

      {!unavailable && <details className="resume-text-option" open={byok || undefined}>
        <summary>{byok ? "粘贴简历文字" : "也可以粘贴简历文字"}</summary>
      <form method="post" onSubmit={propose}>
        <div className="field">
          <label htmlFor="resumeText">简历纯文本</label>
          <textarea
            id="resumeText"
            readOnly={busy || disabled}
            value={resumeText}
            onChange={(event) => {setResumeText(event.target.value); setCallPlan(null); setPendingAction(null);}}
            rows={10}
            maxLength={byok ? 12000 : 30000}
            placeholder="粘贴简历或项目经历文本。"
          />
        </div>
        <div className="actions proposal-actions">
          <button
            className="button"
            type="submit"
            disabled={busy || disabled || resumeText.trim().length < 50}
          >
            {state.kind === "submitting" ? "整理中…" : (authorizeModel ? "查看模型调用计划" : "整理这段简历文本")}
          </button>
          <span className="muted-copy">{resumeText.trim().length} / {byok ? 12000 : 30000} 字符</span>
        </div>
        {source === "text" && !(callPlan && pendingAction) ? feedback : null}
      </form>
      </details>}

      {callPlan && <section className="notice" aria-label="确认本次模型调用">
        <h3>确认本次模型调用</h3>
        <p>简历文本将发给 {callPlan.destination ? `${callPlan.destination} 的 ` : ""}{callPlan.model}。最多发送 {callPlan.maxProviderCalls} 次，最多输出 {callPlan.maxOutputTokens} 个模型计量单位；费用由模型账户承担，此处不估价。</p>
        <button className="button" type="button" disabled={busy || disabled} onClick={executePlan}>{pendingAction ? "检查同一请求" : "确认发送简历文字并生成草稿"}</button>
        {pendingAction && feedback}
      </section>}

      {onManualEntry && !hideManualEntry && !proposal && <div className="actions">
        <Button variant={unavailable || state.kind === "error" ? "primary" : "secondary"}
          disabled={busy || disabled} onClick={onManualEntry}>{manualEntryLabel}</Button>
        {state.kind === "error" && <span className="muted-copy">
          {callPlan && pendingAction ? "手动填写不影响查询刚才的请求。" : "想重试解析，可修改输入后重新查看调用计划；不会自动发送。"}
        </span>}
      </div>}

      {proposal ? (
        <div className="proposal-result">
          {proposalApplied && <button className="button" type="button" onClick={onReviewDraft}>去核对并保存职业背景</button>}
          <details className="resume-draft-sources" open={proposalApplied ? undefined : true}>
            <summary>查看这份草稿与简历原文依据</summary>
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

          </details>
          {!proposalApplied && (
            <button
              className="button-secondary"
              type="button"
              disabled={disabled}
              onClick={() => {
                onApply(proposal);
                setProposalApplied(true);
                setState({
                  kind: "success",
                  message: "已用这份 AI 草稿替换当前编辑内容。请检查后再保存。",
                });
              }}
            >
              用这份草稿替换当前编辑内容
            </button>
          )}
        </div>
      ) : null}
    </section>
  );
}
