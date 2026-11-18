import React from "react";
import type {JobRequirement} from "@/lib/contracts";
import {
  requirementCapabilityLabel,
  requirementImportanceLabel,
  requirementTypeLabel,
  sortJobRequirements,
} from "@/lib/job-requirements";

function RequirementCard({requirement}: {requirement: JobRequirement}) {
  const responsibility = requirement.type === "responsibility";
  return (
    <article className="requirement-card">
      {!responsibility ? (
        <div className="tags">
          <span className={`tag importance-${requirement.importance}`}>
            {requirementImportanceLabel(requirement.importance)}
          </span>
          <span className="tag">{requirementTypeLabel(requirement.type)}</span>
          {requirement.normalizedCapability ? (
            <span className="tag">{requirementCapabilityLabel(requirement.normalizedCapability)}</span>
          ) : null}
        </div>
      ) : null}
      <p>{requirement.originalText}</p>
      {requirement.evidenceSpan.trim() !== requirement.originalText.trim() ? (
        <details className="requirement-source">
          <summary>查看岗位原文依据</summary>
          <blockquote>{requirement.evidenceSpan}</blockquote>
        </details>
      ) : (
        <small className="muted-copy">已显示完整的岗位原文依据</small>
      )}
    </article>
  );
}

export function JobRequirementReviewList({requirements}: {requirements: JobRequirement[]}) {
  const qualifications = sortJobRequirements(requirements.filter(item => item.type !== "responsibility"));
  const duties = requirements.filter(item => item.type === "responsibility")
    .sort((a, b) => a.requirementIndex - b.requirementIndex);
  return (
    <div className="requirement-list">
      {qualifications.length > 0 ? (
        <section className="requirement-list" aria-labelledby="job-qualifications">
          <h3 id="job-qualifications">申请条件与加分项</h3>
          {qualifications.map(item => <RequirementCard key={item.id} requirement={item} />)}
        </section>
      ) : null}
      {duties.length > 0 ? (
        <section className="requirement-list" aria-labelledby="job-duties">
          <h3 id="job-duties">入职后要做的事</h3>
          {duties.map(item => <RequirementCard key={item.id} requirement={item} />)}
        </section>
      ) : null}
    </div>
  );
}
