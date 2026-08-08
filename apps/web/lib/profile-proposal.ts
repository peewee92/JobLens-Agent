import type {
  ProfileExtractionProposal,
  SaveProfilePayload,
} from "@/lib/contracts";

export interface ProfileProposalDraft {
  headline: string;
  years: string;
  evidence: SaveProfilePayload["evidence"];
  skills: SaveProfilePayload["skills"];
}

export function isBlankProfileDraft(draft: ProfileProposalDraft): boolean {
  const evidence = draft.evidence[0];
  const skill = draft.skills[0];
  return (
    draft.headline.trim() === "" &&
    draft.years.trim() === "" &&
    draft.evidence.length === 1 &&
    Boolean(evidence) &&
    evidence.key.trim() === "" &&
    evidence.type === "project" &&
    evidence.summary.trim() === "" &&
    evidence.source === "confirmed by user" &&
    draft.skills.length === 1 &&
    Boolean(skill) &&
    skill.name.trim() === "" &&
    skill.level === "working" &&
    skill.evidenceKeys.length === 0
  );
}

export function proposalToProfileDraft(
  proposal: ProfileExtractionProposal,
): ProfileProposalDraft {
  return {
    headline: proposal.headline,
    years: proposal.yearsOfExperience?.toString() ?? "",
    evidence: proposal.evidence.map((item) => ({
      key: item.key,
      type: item.type,
      summary: item.summary,
      source: `resume proposal ${proposal.runId}`,
    })),
    skills: proposal.skills.map((item) => ({
      name: item.name,
      level: item.level,
      evidenceKeys: [...item.evidenceKeys],
    })),
  };
}
