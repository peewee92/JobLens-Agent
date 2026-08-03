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
