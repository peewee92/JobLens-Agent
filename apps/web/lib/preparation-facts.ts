import type {JobPreparationBundle} from "./contracts";

export function preparationFacts(preparation: JobPreparationBundle | null | undefined) {
  const requirements = new Map<string, {text: string; importance: string}>();
  const evidenceSummaries = new Map<string, string>();
  for (const item of preparation?.interviewFacts?.items ?? []) {
    requirements.set(item.requirementId, {text: item.requirementText, importance: item.importance});
    // Only a one-to-one saved binding is unambiguous; never guess array alignment.
    if (item.evidenceIds.length === 1 && item.evidenceSummaries.length === 1 && item.evidenceSummaries[0].trim()) {
      evidenceSummaries.set(item.evidenceIds[0], item.evidenceSummaries[0]);
    }
  }
  for (const item of preparation?.studyChecklist?.items ?? []) {
    requirements.set(item.requirementId, {text: item.requirementText, importance: item.importance});
  }
  for (const story of preparation?.storyFacts?.items ?? []) {
    if (story.evidenceSummary.trim()) evidenceSummaries.set(story.evidenceId, story.evidenceSummary);
  }
  return {requirements, evidenceSummaries};
}
