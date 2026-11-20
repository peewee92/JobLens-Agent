export type CapturedJobDraft = {title: string; company: string; description: string; sourceUrl: string};
export type CaptureDraftApplication = "applied" | "needs_confirmation" | "locked";

export const captureGrades = {
  full_jd: "较完整", partial_jd: "部分描述", card_only: "仅少量内容", unavailable: "没有正文",
};
export const captureMethods = {
  none: "未提取", json_ld: "页面结构化数据", static_html: "静态网页正文",
  playwright_dom: "渲染后的网页正文", playwright_a11y: "渲染后的无障碍文本",
};

type CaptureDetails = {
  qualityGrade: keyof typeof captureGrades;
  extractionMethod: keyof typeof captureMethods;
  diagnostics: {elapsedMs: number};
};

export type CaptureOutcome =
  | {kind: "captured"; draft: CapturedJobDraft; details: CaptureDetails}
  | {kind: "error"; message: string};

const blockers: Record<string, string> = {
  url_capture_forbidden: "岗位链接抓取只在本机开放。",
  url_capture_ssrf_blocked: "这个链接指向不允许访问的网络地址。",
  url_capture_policy_blocked: "这个链接不符合抓取规则，请使用不含登录凭据的公开岗位链接。",
  capture_timeout: "抓取超时，未生成草稿。",
  capture_budget_exceeded: "页面请求或下载内容过多，已停止抓取。",
  response_too_large: "页面内容超过抓取上限。",
  playwright_not_installed: "这个页面需要浏览器渲染，但本机未安装 Playwright 或 Chromium。请手动粘贴，或按本地安装说明启用浏览器抓取。",
  browser_isolation_unavailable: "未能建立浏览器的网络限制，已停止渲染。",
  browser_render_failed: "浏览器没能取得岗位正文。",
  posting_not_found: "页面中没有找到可核对的岗位名称、公司和描述。",
  unsupported_content_type: "链接没有返回 HTML 岗位页面。",
  http_error: "目标页面不可用，岗位可能已下架或链接已变更。",
  request_validation_error: "请输入有效的公开 HTTP 或 HTTPS 岗位链接。",
};
const interventions: Record<string, string> = {
  login_required: "目标页面需要登录。",
  captcha_detected: "目标页面要求完成验证码。",
  anti_bot_challenge: "目标页面限制了访问或触发了验证。",
  unsupported_spa_shell: "这个页面依赖浏览器加载，但没有取得可用正文。",
};
const fallback = "未能抓取岗位草稿。请检查链接，或用浏览器插件和手动粘贴。";
const knownMessage = (messages: Record<string, string>, key: unknown) =>
  typeof key === "string" && Object.hasOwn(messages, key) ? messages[key] : fallback;

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" ? value as Record<string, unknown> : null;
}

export function decodeCapture(status: number, payload: unknown): CaptureOutcome {
  const result = asRecord(payload);
  const error = (message: string): CaptureOutcome => ({kind: "error", message});
  if (status !== 200 || !result) return error(knownMessage(blockers, asRecord(result?.error)?.code));
  if (result.status === "needs_human_intervention") {
    return error(`${knownMessage(interventions, result.interventionReason)}请改用浏览器插件或手动粘贴正文。`);
  }
  if (result.status !== "captured") {
    return error(knownMessage(blockers, Array.isArray(result.blockers) ? result.blockers[0] : null));
  }
  const draft = asRecord(result.draft);
  const diagnostics = asRecord(result.diagnostics);
  if (draft && typeof draft.title === "string" && draft.title.trim() && typeof draft.company === "string" && draft.company.trim() &&
      typeof draft.description === "string" && draft.description.trim() && typeof draft.sourceUrl === "string" &&
      /^https?:\/\//.test(draft.sourceUrl) && typeof diagnostics?.elapsedMs === "number" && Number.isFinite(diagnostics.elapsedMs) &&
      typeof result.qualityGrade === "string" && Object.hasOwn(captureGrades, result.qualityGrade) &&
      typeof result.extractionMethod === "string" && Object.hasOwn(captureMethods, result.extractionMethod)) {
    return {kind: "captured", draft: {title: draft.title, company: draft.company, description: draft.description, sourceUrl: draft.sourceUrl},
      details: {qualityGrade: result.qualityGrade as CaptureDetails["qualityGrade"],
        extractionMethod: result.extractionMethod as CaptureDetails["extractionMethod"], diagnostics: {elapsedMs: diagnostics.elapsedMs}}};
  }
  return error(fallback);
}

export async function captureJobUrl(url: string, signal: AbortSignal, send = fetch): Promise<CaptureOutcome> {
  try {
    const response = await send("/api/job-imports/url-capture", {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({url}), signal,
    });
    return decodeCapture(response.status, await response.json());
  } catch {
    return {kind: "error", message: fallback};
  }
}

export function applyCaptureDraft(
  fields: Record<keyof CapturedJobDraft, {value: string}>, draft: CapturedJobDraft, confirmReplacement: boolean,
): CaptureDraftApplication {
  const keys = ["title", "company", "description", "sourceUrl"] as const;
  if (!confirmReplacement && keys.some(key => fields[key].value !== "" && fields[key].value !== draft[key])) {
    return "needs_confirmation";
  }
  for (const key of keys) fields[key].value = draft[key];
  return "applied";
}
