import type {JobPreparationBundle} from "./contracts";

export function preparationFacts(preparation: JobPreparationBundle | null | undefined) {
  const requirements = new Map<string, {text: string; importance: string}>();
  const evidenceSummaries = new Map<string, string>();
  for (const item of preparation?.interviewFacts?.items ?? []) {
    requirements.set(item.requirementId, {text: item.requirementText, importance: item.importance});
  }
  for (const item of preparation?.studyChecklist?.items ?? []) {
    requirements.set(item.requirementId, {text: item.requirementText, importance: item.importance});
  }
  for (const story of preparation?.storyFacts?.items ?? []) {
    if (story.evidenceSummary.trim()) evidenceSummaries.set(story.evidenceId, story.evidenceSummary);
  }
  return {requirements, evidenceSummaries};
}
