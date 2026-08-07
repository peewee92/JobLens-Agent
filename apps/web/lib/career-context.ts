import type {
  CareerContextReleaseBlockerCode,
  CareerContextReleaseReadiness,
} from "@/lib/contracts";

export type CareerContextBlockerCopy = {
  title: string;
  description: string;
};

const blockerCopies: Record<CareerContextReleaseBlockerCode, CareerContextBlockerCopy> = {
  profile_missing: {
    title: "还没有保存你的职业背景",
    description: "先填写或从简历生成一份背景草稿，再确认保存。",
  },
  profile_headline_missing: {
    title: "请补充你的职业定位",
    description: "用一句话说明你现在擅长什么、希望往哪个方向发展。",
  },
  profile_years_invalid: {
    title: "请检查工作年限",
    description: "工作年限需要是 0 或更大的有效数字。",
  },
  profile_evidence_missing: {
    title: "还缺少能证明你经历的信息",
    description: "至少补充一段真实工作、项目、教育或成果经历。",
  },
  profile_evidence_invalid: {
    title: "有一段经历填写不完整",
    description: "请检查经历简称、内容和信息来源是否都已填写。",
  },
  profile_evidence_keys_duplicated: {
    title: "有重复的经历简称",
    description: "请给每段经历使用不同的简称，方便技能关联。",
  },
  profile_skills_missing: {
    title: "还没有填写可验证的技能",
    description: "至少添加一项技能，并选择能证明这项技能的真实经历。",
  },
  profile_skill_names_duplicated: {
    title: "有重复的技能名称",
    description: "请合并重复技能，避免后续匹配重复计算。",
  },
  profile_skill_evidence_missing: {
    title: "有技能还没有经历支撑",
    description: "请为每项技能至少选择一段能证明它的真实经历。",
  },
  profile_skill_evidence_reference_invalid: {
    title: "有技能关联到了已不存在的经历",
    description: "请重新选择这项技能对应的经历。",
  },
  search_intent_missing: {
    title: "还没有保存你的求职偏好",
    description: "至少填写目标岗位，再保存求职偏好。",
  },
  search_intent_target_roles_missing: {
    title: "请填写想找的岗位",
    description: "例如 AI 应用工程师、Agent 工程师，可以填写多个。",
  },
  search_intent_target_roles_duplicated: {
    title: "目标岗位有重复",
    description: "删除重复岗位名称即可。",
  },
  search_intent_minimum_salary_invalid: {
    title: "请检查最低薪资",
    description: "最低薪资需要是 0 或更大的有效数字。",
  },
};

export function careerContextReleaseBlockerCopy(
  code: CareerContextReleaseBlockerCode,
): CareerContextBlockerCopy {
  return blockerCopies[code];
}

export function careerContextReleaseLabel(
  readiness: CareerContextReleaseReadiness,
): string {
  return readiness.releaseEligible
    ? "你的信息已准备好，可用于后续岗位匹配"
    : "还需要补充一些信息，才能用于后续岗位匹配";
}
