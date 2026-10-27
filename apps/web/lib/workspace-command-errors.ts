/** Human repair instructions for the existing workspace write responses. */
export function workspaceCommandError(payload: unknown, fallback = "操作未完成，请刷新查看原记录后重试。"): string {
  if (!payload || typeof payload !== "object") return fallback;
  const body = payload as {error?: {message?: unknown}; detail?: unknown};
  if (typeof body.error?.message === "string") return body.error.message;
  const repairs: Record<string, string> = {
    evidence_proposal_requirement_invalid: "所选要求不属于这个行动的原始分析，请刷新核对来源。",
    evidence_proposal_requirement_required: "请选择这项成果实际支持的岗位要求，不会自动推断技能。",
    evidence_proposal_action_source_invalid: "行动来源无法核对，不能用于新的职业事实；历史进度仍保留。",
    evidence_proposal_review_required: "请先核对当前职业资料，勾选确认真实事实及技能程度。",
    evidence_proposal_origin_confirmed: "这条原始提案或重新核对提案已经确认，不会再次写入同一条事实。",
    application_rematch_provider_required: "此岗位需要语义匹配，当前零模型路径不会调用模型；请先保留事实，等待单独授权的分析更新。",
    evidence_proposal_profile_stale: "职业资料已变化，不能直接确认旧提案。请先核对当前资料和提案来源，不会自动合并或覆盖事实。",
    evidence_proposal_idempotency_conflict: "这个请求标识已保存了不同的事实，请刷新核对原提案，不会覆盖已有内容。",
    evidence_proposal_actor_mismatch: "提案与当前工作区身份不一致，请返回原工作区核对。",
    evidence_proposal_fact_required: "请填写真实成果摘要和可追溯来源，再提交待确认事实。",
    execution_action_not_done: "请先记录行动完成，再提交实际产生的事实。完成本身不会增加能力。",
    execution_action_not_evidence_grounded: "这个行动没有可追溯的技能与岗位要求，不能直接作为技能证据，请先核对来源。",
    execution_action_status_conflict: "行动状态已被其他操作更新，请刷新后按当前状态继续。",
    application_status_conflict: "投递状态已被其他操作更新，请刷新并核对当前结果。",
    idempotency_key_conflict: "这个请求标识已用于不同的操作，请刷新核对已有记录。",
  };
  return typeof body.detail === "string" ? repairs[body.detail] ?? fallback : fallback;
}
