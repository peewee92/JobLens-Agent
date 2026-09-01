import type {JobPreparationBundle} from "@/lib/contracts";
import type {ApplicationChecklistStepId} from "@/lib/application-checklist-state";

export interface ApplicationChecklistItem {
  id: ApplicationChecklistStepId;
  label: string;
  text: string;
}

export function buildApplicationChecklistItems(preparation: JobPreparationBundle): ApplicationChecklistItem[] {
  const highlights = preparation.resumeDelta?.highlights ?? [];
  const evidenceGaps = preparation.resumeDelta?.evidenceGaps ?? [];
  const studyItems = preparation.studyChecklist?.items ?? [];
  const interviewItems = preparation.interviewFacts?.items ?? [];
  const topHighlight = highlights[0] ?? null;
  const topEvidenceGap = evidenceGaps[0] ?? null;
  const topStudyItem = studyItems[0] ?? null;
  const topInterviewFocus = interviewItems[0] ?? null;

  const highlightText = topHighlight
    ? `${topHighlight.capability}（Evidence：${topHighlight.evidenceIds.join("、") || "已确认"}）`
    : "当前没有可安全突出为岗位优势的已确认 Evidence。";
  const gapText = topEvidenceGap
    ? `${topEvidenceGap.capability}（${topEvidenceGap.status === "missing" ? "Profile 中缺少该能力事实" : "已有技能事实，但缺少已确认 Evidence"}）`
    : topStudyItem
      ? `${topStudyItem.capability}（${topStudyItem.requirementText}）`
      : "当前没有已识别的 Evidence 缺口或面试前补习项。";
  const interviewText = topInterviewFocus
    ? `${topInterviewFocus.requirementText}（优先级：${topInterviewFocus.preparationPriority}）`
    : "当前没有可可靠生成的面试 Requirement 重点。";

  return [
    {id: "highlight", label: "先突出最有把握的真实经历：", text: highlightText},
    {id: "gap", label: "再补最关键的准备缺口：", text: gapText},
    {id: "interview", label: "最后准备最高优先级面试问题：", text: interviewText},
  ];
}
