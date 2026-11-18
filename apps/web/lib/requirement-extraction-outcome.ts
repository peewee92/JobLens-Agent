import {isUncertainMatchResponse} from "@/lib/import-match-batching";
import {userFacingErrorCode} from "@/lib/user-facing-errors";

type ExtractionOutcome =
  | {kind: "saved"}
  | {kind: "rejected"; message: string}
  | {kind: "uncertain"};

function record(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" ? value as Record<string, unknown> : undefined;
}

/** Only structured rejections known to occur before writing override ambiguous 5xx responses. */
export function requirementExtractionOutcome(status: number, body: unknown, jobId: string): ExtractionOutcome {
  const payload = record(body);
  const code = record(payload?.error)?.code;
  if (status === 502 && code === "invalid_requirement_extractor_output") {
    return {kind: "rejected", message: "没能从这份岗位描述整理出可信的岗位要求，本次没有保存结果。请核对原文是否完整；确认后可重新分析，也可先跳过这个岗位。"};
  }
  if (status === 502 && code === "requirement_extractor_failed") {
    return {kind: "rejected", message: "这次岗位要求分析未完成，也没有保存结果。可以确认后重试，或先分析其他岗位。"};
  }
  if (status === 503 && code === "requirement_extractor_unavailable") {
    return {kind: "rejected", message: "岗位要求分析暂时不可用，本次没有保存结果。请等服务恢复后重试，或先处理其他岗位。"};
  }
  if (isUncertainMatchResponse(status)) return {kind: "uncertain"};
  if (status >= 200 && status < 300) {
    return payload?.jobId === jobId && typeof payload.extractionId === "string" && payload.extractionId.length > 0 && Array.isArray(payload.requirements)
      ? {kind: "saved"} : {kind: "uncertain"};
  }
  return {kind: "rejected", message: userFacingErrorCode(typeof code === "string" ? code : null,
    "岗位要求分析没有完成。请核对页面上的岗位描述和分析条件，确认后再试。")};
}
