import type {ApiErrorBody} from "@/lib/contracts";

const messages: Record<string, string> = {
  request_validation_error: "有些填写内容格式不正确，请检查必填项后重试。",
  context_version_conflict: "这份信息刚刚发生了更新。请刷新页面，确认最新内容后再保存。",
  invalid_career_context: "有些背景或求职偏好还不完整，请检查页面提示后再保存。",
  invalid_collector_report: "这个岗位文件格式不正确，请重新从 JobLens 浏览器插件导出。",
  unsupported_collector_version: "这个岗位文件来自不支持的插件版本，请更新插件后重新导出。",
  import_identity_conflict: "这批岗位与已有记录发生冲突，请重新从浏览器插件导出最新文件后再试。",
  resume_document_too_large: "简历文件超过 5 MiB，请压缩文件或换一份更小的文件。",
  unsupported_resume_document: "目前只支持 PDF 或 DOCX 简历。",
  invalid_resume_document: "这个简历文件无法读取，请确认文件没有损坏或加密。",
  resume_text_not_extractable: "没有从简历中读到足够的文字，请换一份文本型 PDF/DOCX，或直接粘贴简历文字。",
  invalid_resume_text: "简历文字太少或格式不合适，请补充更完整的经历内容后重试。",
  profile_extractor_unavailable: "AI 简历整理暂时不可用，你可以稍后重试或直接手动填写。",
  profile_extractor_failed: "这次 AI 简历整理没有成功，请稍后重试。你的背景信息不会被自动保存。",
  invalid_profile_extractor_output: "这次 AI 简历整理结果不完整，请稍后重试。你的背景信息不会被自动保存。",
  job_description_not_extractable: "这个岗位的 JD 内容太少，暂时无法分析岗位要求。",
  requirement_extractor_unavailable: "岗位要求分析暂时不可用，请稍后重试。",
  requirement_extractor_failed: "这次岗位要求分析没有成功，请稍后重试。",
  invalid_requirement_extractor_output: "这次岗位要求分析结果不完整，请稍后重试。",
  semantic_match_inputs_not_ready: "你的职业背景或岗位要求刚刚发生了变化，请刷新页面确认最新内容后再生成完整匹配建议。",
  semantic_matcher_unavailable: "完整匹配建议暂时不可用；你仍可以先参考上方的硬条件判断。",
  semantic_matcher_failed: "这次 AI 匹配分析没有成功，请稍后重试。",
  invalid_semantic_matcher_output: "这次 AI 匹配结果不完整，没有生成正式建议，请稍后重试。",
  feedback_match_report_stale: "这个岗位的推荐刚刚更新了，请根据最新建议重新判断。",
  internal_server_error: "服务暂时出了点问题，请稍后重试。",
};

export function userFacingErrorCode(
  code: string | null | undefined,
  fallback: string,
): string {
  return code ? messages[code] ?? fallback : fallback;
}

export function userFacingApiError(
  body: Partial<ApiErrorBody> | null | undefined,
  fallback: string,
): string {
  return userFacingErrorCode(body?.error?.code, fallback);
}
