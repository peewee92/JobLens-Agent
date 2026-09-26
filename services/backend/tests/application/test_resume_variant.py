from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.application.application_workspace.models import ApplicationWorkspaceSourceSnapshot
from app.application.application_workspace.resume_variant import BuildResumeVariantProposalUseCase, ResumeVariantBlockedError, SaveResumeVariantUseCase
from app.application.job_preparation.resume_delta import ResumeDeltaEvidenceGap, ResumeDeltaFacts, ResumeDeltaGapStatus, ResumeDeltaHighlight

NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)


class WorkspaceRepo:
    def __init__(self, workspace): self.workspace = workspace
    def get(self, workspace_id): return self.workspace if workspace_id == self.workspace.workspace_id else None


class Preparation:
    def __init__(self, bundle): self.bundle = bundle
    def execute(self, job_id): return self.bundle


class Variants:
    def __init__(self): self.saved = {}; self.added = []
    def get_by_actor_and_idempotency_key(self, actor_id, key): return self.saved.get((actor_id, key))
    def add(self, *, variant, actor_id, idempotency_key):
        self.saved[(actor_id, idempotency_key)] = variant; self.added.append(variant); return variant


def workspace():
    return SimpleNamespace(workspace_id="ws_1", job_id="job_1", source_snapshot=ApplicationWorkspaceSourceSnapshot("prof_1", 3, "intent_1", 2, "req_1", "match_1"))


def bundle(*, profile_version=3):
    delta = ResumeDeltaFacts("job_1", True, "prof_1", profile_version, "req_1", (ResumeDeltaHighlight("r1", "Python", ("s1",), ("ev1",)),), (ResumeDeltaEvidenceGap("r2", "Ray", ResumeDeltaGapStatus.MISSING, ()),), ())
    return SimpleNamespace(facts_usable=True, profile_id="prof_1", profile_version=profile_version, extraction_id="req_1", resume_delta=delta)


def test_proposal_reuses_grounded_resume_delta_and_keeps_gaps_out_of_variant_content():
    proposal = BuildResumeVariantProposalUseCase(workspaces=WorkspaceRepo(workspace()), preparation=Preparation(bundle())).execute("ws_1")
    assert proposal.highlights[0].requirement_id == "r1"
    assert proposal.highlights[0].evidence_ids == ("ev1",)
    assert proposal.unresolved_requirement_ids == ("r2",)


def test_proposal_fails_closed_when_workspace_snapshot_is_stale():
    with pytest.raises(ResumeVariantBlockedError, match="application_workspace_facts_stale"):
        BuildResumeVariantProposalUseCase(workspaces=WorkspaceRepo(workspace()), preparation=Preparation(bundle(profile_version=4))).execute("ws_1")


def test_save_is_idempotent_and_never_saves_unevidenced_gap_as_resume_content():
    proposals = BuildResumeVariantProposalUseCase(workspaces=WorkspaceRepo(workspace()), preparation=Preparation(bundle()))
    variants = Variants()
    use_case = SaveResumeVariantUseCase(proposals=proposals, variants=variants, now=lambda: NOW, new_id=lambda: "rv_1")
    first = use_case.execute(workspace_id="ws_1", actor_id="user_1", idempotency_key="save-1")
    second = use_case.execute(workspace_id="ws_1", actor_id="user_1", idempotency_key="save-1")
    assert first == second
    assert len(variants.added) == 1
    assert first.highlights[0].evidence_ids == ("ev1",)
