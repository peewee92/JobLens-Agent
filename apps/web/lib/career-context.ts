import type {
  CareerContextReleaseBlockerCode,
  CareerContextReleaseReadiness,
} from "@/lib/contracts";

export const careerContextReleaseBlockerLabels: Record<
  CareerContextReleaseBlockerCode,
  string
> = {
  profile_missing: "尚未确认职业画像版本",
  profile_headline_missing: "职业画像标题为空",
  profile_years_invalid: "工作年限无效",
  profile_evidence_missing: "职业画像缺少 Evidence",
  profile_evidence_invalid: "Evidence 的 key、摘要或来源不完整",
  profile_evidence_keys_duplicated: "Evidence key 重复",
  profile_skills_missing: "职业画像缺少可验证技能",
  profile_skill_names_duplicated: "技能名称重复",
  profile_skill_evidence_missing: "技能没有关联 Evidence",
  profile_skill_evidence_reference_invalid: "技能引用了不存在的 Evidence",
  search_intent_missing: "尚未确认求职意向版本",
  search_intent_target_roles_missing: "求职意向缺少目标岗位",
  search_intent_target_roles_duplicated: "目标岗位重复",
  search_intent_minimum_salary_invalid: "最低薪资无效",
};

export function careerContextReleaseLabel(
  readiness: CareerContextReleaseReadiness,
): string {
  return readiness.releaseEligible
    ? "个人侧事实已可供未来 Match 使用"
    : "个人侧事实尚未通过 Match 输入门禁";
}
